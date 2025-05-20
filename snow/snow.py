#!/usr/bin/env python3

import click
from .util import login, list_tasks, show_ticket, patch, ticket_yaml, comments, ticket_properties, ticket as ticket_util
from colorama import Fore, Back, Style # For terminal colours
from pprint import pprint

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


@click.group(cls=AliasedGroup)
@click.option('--debug', "-d", is_flag=True, default=False)
@click.option('--format', "-f", default="table", help='Output format')
@click.pass_context
def snow(ctx, debug, format):
    ctx.ensure_object(dict)
    ctx.obj["BASE_URL"] = login.BASE_URL
    ctx.obj["s"] = login.login()
    ctx.obj["debug"] = debug
    ctx.obj["format"] = format
    ctx.obj["api"] = False
    pass


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
        if not comments:
            print(f"{number} has no comments")
            continue
        #pprint(comments)
        last_comment = comments[-1]
        last_comment_by = last_comment["sys_created_by"]["value"]
        last_comment_on = last_comment["sys_created_on"]["value"]
        print(f"{number}: Latest comment at {last_comment_on} by {last_comment_by}")
        emails = ticket_util.get_emails_for_ticket(ctx.obj, id)
        # Filter to just emails notifying the requestor
        emails = [e for e in emails if requestor_email in e["recipients"]["value"]]
        if not emails:
            print(f"{Fore.RED}No emails to {requestor_email} on ticket {number}{Style.RESET_ALL}")
        else:
            last_email = emails[-1]
            last_email_by = last_email["sys_created_by"]["value"]
            last_email_on = last_email["sys_created_on"]["value"]
            last_email_to = last_email["recipients"]["value"]
            subject = last_email["subject"]["value"]
            print(f"Latest email at {last_email_on} to {last_email_to}: {subject}")
            if last_email_on < last_comment_on:
    #            pprint(last_email)
    #            pprint(last_comment)
                print(f"{Fore.RED}No email notifying {requestor_email} sent for last comment on ticket {number} by {last_comment_by}{Style.RESET_ALL}")
        print("-"*10)


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
    """Get only comments from users, excluding automation comments"""
    comments.get_user_comments(ctx.obj, number)


@snow.command(name="get_ticket_status")
@click.argument('number')
@click.pass_context
def get_ticket_status(ctx, number):
    """Get ticket status"""
    ticket_properties.get(ctx, number, "state")


@snow.command(name="comment")
@click.argument('number')
@click.pass_context
def comment(ctx, number):
    """Add a comment"""
    patch.patch(ctx.obj, number, "comments")


@snow.command(name="worknotes")
@click.argument("number")
@click.pass_context
def worknotes(ctx, number):
    """Add worknotes"""
    patch.patch(ctx.obj, number, "work_notes")


@snow.command(name="resolve")
@click.argument("number")
@click.pass_context
def resolve(ctx, number):
    """Resolve a ticket"""
    patch.patch(ctx.obj, number, "resolve")


@snow.command(name="set_third_party_reference")
@click.argument("number")
@click.pass_context
def set_third_party_reference(ctx, number):
    """Set third party reference"""
    patch.patch(ctx.obj, number, "u_third_party_reference")


@snow.command(name="set_customer_promise")
@click.argument("number")
@click.pass_context
def set_customer_promise(ctx, number):
    """Set customer promise"""
    patch.patch(ctx.obj, number, "u_customer_promise")


if __name__ == '__main__':
    snow(obj={})
