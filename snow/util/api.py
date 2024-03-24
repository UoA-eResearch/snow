from . import login, comments, ticket_properties, patch, ticket


class Snow:
    def __init__(self):
        self.ctx = {
            "BASE_URL": login.BASE_URL,
            "s": login.login(),
            "api": True
        }

    def get_user_comments(self, ticket_number):
        return comments.get_user_comments(self.ctx, ticket_number)

    def get_ticket_property(self, ticket_number, property):
        return ticket_properties.get(self.ctx, ticket_number, property)

    def patch_ticket_property(self, ticket_number, property, value):
        return ticket_properties.patch(self.ctx, ticket_number, property, value)

    def add_worknote(self, ticket_number, message):
        return patch.patch(self.ctx, ticket_number, "work_notes", message)

    def get_work_notes(self, ticket_number):
        t = ticket.get_ticket(self.ctx, ticket_number)
        work_notes = t['work_notes']
        return work_notes
