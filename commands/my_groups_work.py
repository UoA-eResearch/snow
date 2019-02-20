import util

def run(BASE_URL, s, args):
    query = "assignment_group=javascript:getMyGroups()^active=true"
    if "assigned" not in args:
        # don't get assigned tickets by default
        query += "^assigned_to="
    if "resolved" not in args:
        # don't get resolved tickets by default
        query += "^stateNOT IN-16,6,-2,-3"
    
    util.get_and_print_filtered_tasks(query)