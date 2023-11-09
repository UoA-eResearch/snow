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
Usage: snow.py [OPTIONS] COMMAND [ARGS]...

Options:
  -d, --debug
  -f, --format TEXT  Output format
  --help             Show this message and exit.

Commands:
  comment                    Add a comment
  extract_yaml               Write original request to file
  my_groups_work             Show tickets in your groups
  my_work                    Show your tickets
  resolve                    Resolve a ticket
  set_third_party_reference  Set third party reference
  show                       Show a ticket
  worknotes                  Add worknotes
  ```