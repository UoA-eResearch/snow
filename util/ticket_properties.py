#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from .ticket import get_ticket


def get_ticket_status(ctx, ticket_number):
    ticket = get_ticket(ctx, ticket_number)
    status = ticket['state']
    if not ctx["api"]:
        print(status)
    return status
