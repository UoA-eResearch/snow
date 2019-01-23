#!/usr/bin/env python

import util
import sys
from six.moves import input

def handle_command(command):
    command = command.lower().replace(" ", "_")
    if command == "help":
        for command in util.commands:
            print(command.replace("_", " "))
    else:
        for plugincommand in util.commands:
            if command == plugincommand:
                return util.commands[plugincommand](util.BASE_URL, util.s)
        print("Command not found")

if len(sys.argv) > 1:
  input = ' '.join(sys.argv[1:])
  handle_command(input)
else:
  #REPL
  while True:
    print("Type a command, or type help to list commands")
    command = input()
    try:
      handle_command(command)
    except Exception as e:
      print(e)