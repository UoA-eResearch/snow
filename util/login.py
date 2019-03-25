import requests
from urlparse import urlparse, parse_qs
import config
from bs4 import BeautifulSoup
import pickle
import os
import sys
from six.moves import input
import re

BASE_URL = "https://uoaprod.service-now.com/"
INCORRECT_CREDENTIAL_STRING = "The combination of credentials you have entered is incorrect"
INCORRECT_2FA_STRING = "The token you have entered is not correct"

def login():
    # Load a previous session if one exists, otherwise make a new session
    try:
        with open('session_cache') as f:
            s = pickle.load(f)
    except IOError:
        s = requests.Session()

    # Make a simple request to see if a login is required
    r = s.get(BASE_URL)

    if "auth_redirect" in r.url:
        # SSO redirection - login
        parsed_url = urlparse(r.url)
        params = parse_qs(parsed_url.query)
        sysparm_url = params['sysparm_url'][0]

        r = s.get(sysparm_url)
        print("Navigated to " + r.url)
        if r.url == "https://iam.auckland.ac.nz/profile/SAML2/Redirect/SSO?execution=e1s1":
            r = s.post(r.url, { "j_username": config.username, "j_password": config.password, "submitted": 0, "_eventId_proceed": "" })
            print("Entered username and password")
            if INCORRECT_CREDENTIAL_STRING in r.content:
                print(INCORRECT_CREDENTIAL_STRING + ". Check config.py")
                exit(1)
            while "j_token" in r.content:
                two_factor = input("Please enter your 2FA token: ")
                r = s.post(r.url, { "submitted": "", "j_token": two_factor, "rememberMe": "on", "_eventId_proceed": "" })
                if INCORRECT_2FA_STRING in r.content:
                    print("Incorrect 2FA token, try again: ")
            soup = BeautifulSoup(r.content, 'html.parser')
            # login success, submit form
            form = {}
            form_inputs = soup.find_all("input", attrs = {'name' : True})
            for input_elem in form_inputs:
                form[input_elem['name']] = input_elem['value']
            r = s.post(form['RelayState'], form)
            print("Navigated to " + r.url)
            csrf_token = re.search(r"var g_ck = '(\w+)';", r.content).group(1)
            s.headers['X-UserToken'] = csrf_token
            with open('session_cache', 'w') as f:
                pickle.dump(s, f)


    return s