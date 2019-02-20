import util

def run(BASE_URL, s, args):
    query = "assignment_group=javascript:getMyGroups()^active=true^assigned_toANYTHING"
    util.get_and_print_filtered_tasks(query)