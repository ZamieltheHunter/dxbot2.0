import os
import time
import re

import psycopg2

from slackclient import SlackClient
from lib.quotes import addQuote, getQuote

# Create client
client = SlackClient(os.environ.get('DXBOT_TOKEN'))
# User ID: Set after connecting
dxbot_id = None
users = []
user_map = {}
last_event = None

# Constants
READ_DELAY = 1  # 1 second read delay
COMMAND_CHARACTER = os.getenv('COMMAND_CHARACTER', '!')
COMMAND_REGEX = r"^" + re.escape(COMMAND_CHARACTER) + r"(?P<command>\w+) ?(?P<message>.*)?$"
CONNECT_STRING = 'dbname={} user={} host={} password={}'.format(
    os.getenv('DB_NAME', 'dxbot'),
    os.getenv('DB_USER', 'postgres'),
    os.getenv('DB_HOST', 'localhost'),
    os.getenv('DB_PASS', '')
)

EXCLUSION_LIST = [
    'slackbot',
    'scryfall',
    'dx_bot',
    'dx_cal_bot',
    'resistance_bot'
]


def db_install():
    try:
        conn = psycopg2.connect(CONNECT_STRING)
        cur = conn.cursor()
        cur.execute('SELECT * FROM quotes;')
        cur.close()
    except psycopg2.Error as e:
        if e and e.pgerror and 'does not exist' in e.pgerror:
            conn = psycopg2.connect(CONNECT_STRING)
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE quotes(
                    id      SERIAL          PRIMARY KEY,
                    name    varchar(50)     NOT NULL,
                    quote   varchar(2000)    NOT NULL
                );
                """
            )
            conn.commit()
            cur.close()
        else:
            print('Error connecting to database.')
            exit()


def parse_message(slack_events):
    """
    Parses a list of events coming from the Slack RTM API to find bot commands.
    If a bot command is found, this function retruns a tuple of
    Command, args and channel
    If it is not found, then this function returns None, None
    """
    for event in slack_events:
        if event['type'] == 'message' and 'subtype' not in event:
            global last_event
            prev = last_event
            last_event = event if not event['text'].startswith(COMMAND_CHARACTER) else last_event
            command, args = parse_command(event['text'])
            if command:
                return command, args, event['channel'], prev
    return None, None, None, None


def parse_command(message_text):
    """
    Finds a direct mention (a mention that is at the beginning) in message text
    and returns the user ID which was mentioned. If there is no direct mention,
    returns None
    """
    matches = re.search(COMMAND_REGEX, message_text, re.IGNORECASE)
    if matches:
        command = matches.group('command')
        if len(matches.groups()) > 1 and matches.group('message') != '':
            return (command, matches.group('message'))
        return (command, None)
    return (None, None)


def handle_command(command, args, channel, prev):
    """
    Executes bot command if the command is known
    """

    default_response = 'That is not a valid command.'

    response = None
    if command.startswith('quote'):
        if args is not None and len(args.split()) > 1:
            response = addQuote(args, users)
        else:
            response = getQuote(args, users)
    if command.startswith('lookup'):
        if args is not None and len(args.split()) = 1:
            response = getQuoteByLookup(args, users)
        else:
            response = 'Too many arguments provided'
    if command.startswith('grab'):
        message = '{} {}'.format(user_map[prev['user']], prev['text'])
        response = addQuote(message, users)

    client.api_call(
        'chat.postMessage',
        channel=channel,
        text=response or default_response
    )


if __name__ == "__main__":
    db_install()
    if client.rtm_connect(with_team_state=False):
        print('dxbot has connected')
        dxbot_id = client.api_call('auth.test').get('user_id')
        users = [
            member['name']
            for member
            in client.api_call('users.list')['members']
            if member['name'] not in EXCLUSION_LIST
        ]
        user_map = {
            member['id']: member['name']
            for member
            in client.api_call('users.list')['members']
            if member['name'] not in EXCLUSION_LIST
        }
        while True:
            command, args, channel, prev = parse_message(client.rtm_read())
            if command:
                handle_command(command, args, channel, prev)
            time.sleep(READ_DELAY)
