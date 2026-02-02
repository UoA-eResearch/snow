# snow
A simple command line interface to Service Now, written in Python. Supports SSO / 2FA.

## Installation
Copy config.py.example to config.py and replace with your SSO credentials.  
`sudo pip3 install -r requirements.txt`

## Usage

`./snow.py --help`  
or
`python snow.py --help`  

To show my groups work:
`./snow.py my_groups_work`

Output of `./snow.py --help`

```
Usage: snow [OPTIONS] COMMAND [ARGS]...

Options:
  -d, --debug
  -f, --format TEXT  Output format (text or json)
  --help             Show this message and exit.

Commands:
  comment                    Add a comment
  email_check                Check missing emails for the latest comment
  extract_yaml               Write original request to file
  get_ticket_status          Get ticket status
  get_user_comments          Get only msg from users, not automation
  my_groups_work             Show tickets in your groups
  my_work                    Show your tickets
  resolve                    Resolve a ticket
  set_customer_promise       Set customer promise
  set_third_party_reference  Set third party reference
  show                       Show a ticket
  worknotes                  Add worknotes
  ```