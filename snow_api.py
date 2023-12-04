from util import login, comments, ticket_properties


class Snow:
    def __init__(self):
        self.ctx = {
            "BASE_URL": login.BASE_URL,
            "s": login.login(),
            "api": True
        }

    def get_user_comments(self, ticket_number):
        return comments.get_user_comments(self.ctx, ticket_number)

    def get_ticket_status(self, ticket_number):
        return ticket_properties.get_ticket_status(self.ctx, ticket_number)
