#!/usr/bin/env python3

import os
import sys

import click
import requests
from .util import (
    login, list_tasks, show_ticket, patch, ticket_yaml,
    comments, ticket_properties, ticket as ticket_util
)
from .util.output import (
    CommandFailed, report_failure, emit_json, error_document, diag,
    EXIT_ERROR, EXIT_USAGE, EXIT_LOGIN_REQUIRED,
)
from colorama import Fore, Style  # For terminal colours


def _env_flag(name):
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


class SnowContext(dict):
    """ctx.obj for the CLI. Logs in lazily, the first time a command needs
    the HTTP session (ctx.obj["s"]), so `snow <command> --help` works
    without touching the network."""

    def __missing__(self, key):
        if key != "s":
            raise KeyError(key)
        s = login.login(interactive=not self["non_interactive"])
        s.hooks.setdefault("response", []).append(login.raise_on_unauthenticated)
        self["s"] = s
        return s


class AliasedGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        for x in self.list_commands(ctx):
            initials = "".join([c[0] for c in x.split("_")])
            if cmd_name == initials:
                return click.Group.get_command(self, ctx, x)
        return None

    def invoke(self, ctx):
        # Turn every failure inside a command into the documented contract:
        # one JSON document on stdout in json mode, diagnostics on stderr,
        # and a distinct exit code.
        try:
            return super().invoke(ctx)
        except CommandFailed as e:
            report_failure(ctx.obj, e)
            ctx.exit(e.exit_code)
        except login.LoginRequired as e:
            if _json_mode(ctx):
                emit_json(error_document("login_required", e.message,
                                         {"reason": e.reason}))
            else:
                diag(e.message)
            ctx.exit(EXIT_LOGIN_REQUIRED)
        except click.UsageError as e:
            if not _json_mode(ctx):
                raise
            e.show()  # usual usage message on stderr
            emit_json(error_document("usage_error", e.format_message()))
            ctx.exit(EXIT_USAGE)
        except (click.exceptions.Exit, click.exceptions.Abort, click.ClickException):
            raise
        except requests.RequestException as e:
            if not _json_mode(ctx):
                raise
            diag("Network error: %s" % e)
            emit_json(error_document("network_error", str(e)))
            ctx.exit(EXIT_ERROR)
        except Exception as e:
            if not _json_mode(ctx):
                raise
            import traceback
            traceback.print_exc(file=sys.stderr)
            emit_json(error_document("unexpected_error",
                                     "%s: %s" % (type(e).__name__, e)))
            ctx.exit(EXIT_ERROR)


def _json_mode(ctx):
    return isinstance(ctx.obj, dict) and ctx.obj.get("format") == "json"


@click.group(cls=AliasedGroup)
@click.option('--debug', "-d", is_flag=True, default=False)
@click.option('--format', "-f", default="text", help='Output format (text or json)')
@click.option('--non-interactive', "non_interactive", is_flag=True, default=False,
              help='Never prompt (2FA token, $EDITOR). Exit 3 if a login is '
                   'required. Implied when stdin is not a TTY or '
                   'SNOW_NON_INTERACTIVE=1.')
@click.pass_context
def snow(ctx, debug, format, non_interactive):
    non_interactive = (
        non_interactive
        or _env_flag("SNOW_NON_INTERACTIVE")
        or not sys.stdin.isatty()
    )
    ctx.obj = SnowContext(
        BASE_URL=login.BASE_URL,
        debug=debug,
        format=format,
        api=False,
        non_interactive=non_interactive,
    )


message_option = click.option(
    '--message', '-m', default=None,
    help='Text to write. If omitted, read from stdin when piped, otherwise '
         'open $EDITOR (never in non-interactive mode).')


@snow.command(name="my_groups_work")
@click.option('--assigned', "-a", is_flag=True, show_default=True, default=False, help='Filter by assignment status')
@click.option('--state', "-s", default="open", show_default=True, help='Filter by status')
@click.option('--active', "-l", is_flag=True, show_default=True, default=True, help='Filter by active status')
@click.option('--offboard', "-o", is_flag=True, show_default=True, default=False, help='Include offboarding tickets')
@click.pass_context
def my_groups_work(ctx, assigned, state, active, offboard):
    """Show tickets in your groups"""
    query = "assignment_group=javascript:getMyGroups()^sys_class_name!=u_security_vulnerabilities^ORDERBYnumber"
    if not assigned:
        query += "^assigned_toISEMPTY"
    if active:
        query += "^active=true"
    if state in ["open", "unresolved", "unsolved"]:
        query += "^stateNOT IN-16,6,-2,-3"
    elif state in ["closed", "resolved", "solved"]:
        query += "^stateIN-16,6,-2,3"
    if not offboard:
        query += "^u_third_party_referenceNOT LIKEOffboard^ORu_third_party_referenceISEMPTY"

    list_tasks.get_and_print_filtered_tasks(ctx.obj, query)


@snow.command(name="email_check")
@click.option('--assigned', "-a", is_flag=True, show_default=True, default=True, help='Filter by assignment status')
@click.option('--state', "-s", default="open", show_default=True, help='Filter by status')
@click.option('--active', "-l", is_flag=True, show_default=True, default=True, help='Filter by active status')
@click.option('--offboard', "-o", is_flag=True, show_default=True, default=False, help='Include offboarding tickets')
@click.pass_context
def email_check(ctx, assigned, state, active, offboard):
    """Check missing emails for the latest comment"""
    query = "assignment_group=javascript:getMyGroups()^sys_class_name!=u_security_vulnerabilities^ORDERBYnumber"
    if not assigned:
        query += "^assigned_toISEMPTY"
    if active:
        query += "^active=true"
    if state in ["open", "unresolved", "unsolved"]:
        query += "^stateNOT IN-16,6,-2,-3"
    elif state in ["closed", "resolved", "solved"]:
        query += "^stateIN-16,6,-2,3"
    if not offboard:
        query += "^u_third_party_referenceNOT LIKEOffboard^ORu_third_party_referenceISEMPTY"

    tickets = list_tasks.get_filtered_tasks(ctx.obj, query)
    if tickets is None:
        return

    results = []
    for ticket in tickets:
        number = ticket["number"]["value"]
        if number.startswith("SCTASK"):
            # Get RITM parent, as that's where the email records are
            number = ticket["parent"]["display_value"]
            id = ticket["parent"]["value"]
        elif number.startswith("INC"):
            id = ticket["sys_id"]["value"]
        else:
            continue

        if ticket["u_requestor"]["display_value"] == 'CeR RESTAPI':
            requestor_id = ticket["u_affected_contact"]["value"]
        else:
            requestor_id = ticket["u_requestor"]["value"]
        # Populate a full user object, to get the requestor's UPI and email address
        requestor = ticket_util.get_user_by_sys_id(ctx.obj, requestor_id)
        requestor_email = requestor.get("email")
        requestor_upi = requestor.get("user_name")
        comments = ticket_util.get_comments_for_ticket(ctx.obj, id)
        # Filter out comments by the requestor, and filter out work_notes
        comments = [c for c in comments if c["sys_created_by"]["value"] != requestor_upi and c["element"]["value"] == "comments"]

        ticket_result = {
            "ticket_number": number,
            "has_comments": len(comments) > 0
        }

        if not comments:
            ticket_result["status"] = "no_comments"
            if ctx.obj["format"] == "text":
                print(f"{number} has no comments")
            results.append(ticket_result)
            continue

        last_comment = comments[-1]
        last_comment_by = last_comment["sys_created_by"]["value"]
        last_comment_on = last_comment["sys_created_on"]["value"]

        ticket_result["last_comment"] = {
            "by": last_comment_by,
            "on": last_comment_on
        }

        if ctx.obj["format"] == "text":
            print(f"{number}: Latest comment at {last_comment_on} by {last_comment_by}")

        emails = ticket_util.get_emails_for_ticket(ctx.obj, id)
        # Filter to just emails notifying the requestor
        emails = [e for e in emails if requestor_email in e["recipients"]["value"]]

        if not emails:
            ticket_result["status"] = "no_emails"
            ticket_result["requestor_email"] = requestor_email
            if ctx.obj["format"] == "text":
                print(f"{Fore.RED}No emails to {requestor_email} on ticket {number}{Style.RESET_ALL}")
        else:
            last_email = emails[-1]
            last_email_by = last_email["sys_created_by"]["value"]
            last_email_on = last_email["sys_created_on"]["value"]
            last_email_to = last_email["recipients"]["value"]
            subject = last_email["subject"]["value"]

            ticket_result["last_email"] = {
                "by": last_email_by,
                "on": last_email_on,
                "to": last_email_to,
                "subject": subject
            }

            if ctx.obj["format"] == "text":
                print(f"Latest email at {last_email_on} to {last_email_to}: {subject}")

            if last_email_on < last_comment_on:
                ticket_result["status"] = "email_outdated"
                ticket_result["requestor_email"] = requestor_email
                if ctx.obj["format"] == "text":
                    print(f"{Fore.RED}No email notifying {requestor_email} sent for last comment on ticket {number} by {last_comment_by}{Style.RESET_ALL}")
            else:
                ticket_result["status"] = "ok"

        results.append(ticket_result)
        if ctx.obj["format"] == "text":
            print("-"*10)

    if ctx.obj["format"] == "json":
        emit_json(results)


@snow.command(name="my_work")
@click.option('--state', "-s", default="open", help='Filter by status')
@click.pass_context
def mw(ctx, state):
    """Show your tickets"""
    query = "active=true^assigned_to=javascript:getMyAssignments()^ORDERBYnumber"

    if state in ["open", "unresolved", "unsolved"]:
        query += "^stateNOT IN-16,6,-2,-3"
    elif state in ["closed", "resolved", "solved"]:
        query += "^stateIN-16,6,-2,3"

    list_tasks.get_and_print_filtered_tasks(ctx.obj, query)


@snow.command(name="show")
@click.argument('number')
@click.pass_context
def show(ctx, number):
    """Show a ticket"""
    show_ticket.get_and_print_ticket(ctx.obj, number)


@snow.command(name="extract_yaml")
@click.argument('number')
@click.pass_context
def download_yaml(ctx, number):
    """Write original request to file"""
    ticket_yaml.extract(ctx.obj, number)


@snow.command(name="get_user_comments")
@click.argument('number')
@click.pass_context
def get_user_comments(ctx, number):
    """Get only msg from users, not automation"""
    comments.get_user_comments(ctx.obj, number)


@snow.command(name="get_ticket_status")
@click.argument('number')
@click.pass_context
def get_ticket_status(ctx, number):
    """Get ticket status"""
    ticket_properties.get(ctx.obj, number, "state")


@snow.command(name="comment")
@click.argument('number')
@message_option
@click.pass_context
def comment(ctx, number, message):
    """Add a comment"""
    patch.patch(ctx.obj, number, "comments", message)


@snow.command(name="worknotes")
@click.argument("number")
@message_option
@click.pass_context
def worknotes(ctx, number, message):
    """Add worknotes"""
    patch.patch(ctx.obj, number, "work_notes", message)


@snow.command(name="resolve")
@click.argument("number")
@message_option
@click.pass_context
def resolve(ctx, number, message):
    """Resolve a ticket"""
    patch.patch(ctx.obj, number, "resolve", message)


@snow.command(name="set_third_party_reference")
@click.argument("number")
@message_option
@click.pass_context
def set_third_party_reference(ctx, number, message):
    """Set third party reference"""
    patch.patch(ctx.obj, number, "u_third_party_reference", message)


@snow.command(name="set_customer_promise")
@click.argument("number")
@message_option
@click.pass_context
def set_customer_promise(ctx, number, message):
    """Set customer promise"""
    patch.patch(ctx.obj, number, "u_customer_promise", message)


if __name__ == '__main__':
    snow(obj={})
