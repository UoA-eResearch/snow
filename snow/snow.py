#!/usr/bin/env python3

import click
from .util import login, list_tasks, show_ticket, patch, ticket_yaml, comments, ticket_properties


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
@click.option('--assigned', "-a", default="false", help='Filter by assignment status')
@click.option('--state', "-s", default="open", help='Filter by status')
@click.option('--active', "-l", default="true", help='Filter by active status')
@click.pass_context
def my_groups_work(ctx, assigned, state, active):
    """Show tickets in your groups"""
    query = "assignment_group=javascript:getMyGroups()^ORDERBYnumber"
    if assigned in ["no", "false", "noone"]:
        query += "^assigned_toISEMPTY"
    if active in ["true", "yes"]:
        query += "^active=true"
    if state in ["open", "unresolved", "unsolved"]:
        query += "^stateNOT IN-16,6,-2,-3"
    elif state in ["closed", "resolved", "solved"]:
        query += "^stateIN-16,6,-2,3"

    list_tasks.get_and_print_filtered_tasks(ctx.obj, query)


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
