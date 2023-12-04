#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import re
from .ticket import get_ticket


def get_user_comments(ctx, ticket_number):
    ticket = get_ticket(ctx, ticket_number)
    comments = ticket['comments']
    pattern = r'(\d{2}-\d{2}-\d{4}\s\d{2}:\d{2}:\d{2})'
    comments = re.split(pattern, comments)
    response = []
    for i in range(1, len(comments), 2):
        date = comments[i]
        comment = comments[i+1]
        name = comment.split('\n')[0].split(' - ')[1].split(' (')[0]
        comment_content = '\n'.join(comment.split('\n')[1:])
        if (name == 'Guest' and "cid:logo.png" in comment_content) or "APIGateway" in name:
            continue
        if not ctx["api"]:
            print('------------------ New comment ------------------')
            print(f'Comment by {name} on {date}')
            print(comment_content)
        response.append({
            'name': name,
            'date': date,
            'comment': comment_content
        })
    return response
