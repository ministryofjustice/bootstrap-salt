import base64
import hashlib
import logging
import os
from slugify import slugify
import requests


# Set up the logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap-cfn::github")
logging.getLogger("requests").setLevel(logging.WARNING)


API_ENDPOINT = 'https://api.github.com/'
DEFAULT_ORG_SLUG = 'ministryofjustice'


class GithubTokenMissing(Exception):
    pass


class GithubRequestException(Exception):
    pass


class InvalidTeamException(Exception):
    pass


class InvalidKey(Exception):
    pass


def get_github_token():
    """
    Get the github token from the GH_TOKEN environment variable

    Returns:
        (string): String of the github auth token

    Raises:
         GithubTokenMissing: If no token env variable was found
    """
    if 'GH_TOKEN' not in os.environ:
        raise GithubTokenMissing('GH_TOKEN has not been defined.')
    return os.environ['GH_TOKEN']


def get_paginated_content(url,
                          page=None,
                          out=None,
                          **kwargs):
    """
    Helper function to get information from the github API,
    and handle any paging.

    Args:
        url(string): The API url endpoint to contact
        page(int): DEPRECATED: The page number of the
            paginated requests to retrieve.
        out(list): Output list to append results to.
        kwargs(dictionary): Other API call parameters
    """
    per_page = 100

    # Ensure out defaults to an empty list
    if out is None:
        out = []

    # Ensure we have a params entry in kwargs
    if 'params' not in kwargs:
        kwargs['params'] = {}

    # if we have paging, update the url
    if page is not None:
        logger.warning("get_paginated_content: "
                       "page value is deprecated, ignoring "
                       " specified value '{}'..."
                       .format(page))
    if 'auth' not in kwargs:
        kwargs['auth'] = (get_github_token(), 'x-oauth-basic')

    kwargs['params'].update({'per_page': per_page})

    # Do requests
    result = requests.get(url, **kwargs)
    if result.status_code != 200:
        raise GithubRequestException('GH API request failed with code: {}'
                                     '\n{}'
                                     .format(result.status_code,
                                             result.text))

    out.extend(result.json())

    # Recursively append paged results to out dictionary
    if 'next' in result.links:
        out = get_paginated_content(result.links['next']['url'],
                                    out=out,
                                    **kwargs)
    return out


def get_teams(org_slug=DEFAULT_ORG_SLUG):
    """
    Get the list of teams in an organisation from github

    Args:
        org_slug(string): The organisation name in slug format

    Returns:
        response(list): List of teams from github
    """
    # Ensure that org name is in slug format
    forced_org_slug = check_slug_format(org_slug)
    url = '{}orgs/{}/teams'.format(API_ENDPOINT, forced_org_slug)
    response = get_paginated_content(url)
    return response


def get_org_members(org_slug=DEFAULT_ORG_SLUG):
    """
    Get a list of members in an organisation

    Args:
        org_slug(string): The organisation name in slug format

    Returns:
        response(list): List of organisation members from github
    """
    # Ensure that org name is in slug format
    forced_org_slug = check_slug_format(org_slug)

    url = '{}orgs/{}/members'.format(forced_org_slug)
    return get_paginated_content(url)


def get_org_team(team_slug, org_slug=DEFAULT_ORG_SLUG):
    """
    Get team information in an organisation from github

    Args:
        team_slug(string): The team name in slug format
        org_slug(string): The organisation name in slug format

    Returns:
        (dict): Dictionary of the response team information from github
    """
    # Ensure that org name is in slug format
    forced_org_slug = check_slug_format(org_slug)
    # Ensure that team name is in slug format
    forced_team_slug = check_slug_format(team_slug)
    teams = get_teams(forced_org_slug)
    team = filter(lambda x: x['slug'] == forced_team_slug, teams)
    if len(team) == 0:
        raise InvalidTeamException('Team {} is not part of org {}'
                                   .format(forced_team_slug,
                                           forced_org_slug))
    else:
        return team[0]


def get_team_members(team_slug, org_slug=DEFAULT_ORG_SLUG):
    """
    Get the names of the team members of a team in an
    organisation.

    Args:
        team_slug(string): The team name in slug format
        org_slug(string): The organisation name in slug format

    Returns:
        (list): List of team members from github
    """
    # Ensure that team name is in slug format
    forced_team_slug = check_slug_format(team_slug)
    # Ensure that org name is in slug format
    forced_org_slug = check_slug_format(org_slug)

    try:
        team = get_org_team(forced_team_slug, forced_org_slug)
    except InvalidTeamException:
        return {}
    url = '{}teams/{}/members'.format(API_ENDPOINT, team['id'])
    return get_paginated_content(url)


def check_org_membership(org_slug, user_slug):
    """
    Check that a user is a member of an organisation

    Args:
        org_slug(string): The organisation name in slug format
        user_slug(string): The user name in slug format

    Returns:
        (bool): True is user is a mamber of the organisation,
            False otherwise.
    """
    # Ensure that team name is in slug format
    forced_org_slug = check_slug_format(org_slug)
    # Ensure that team name is in slug format
    forced_user_slug = check_slug_format(user_slug)
    url = ('{}orgs/{}/members/{}'
           .format(API_ENDPOINT,
                   forced_org_slug,
                   forced_user_slug)
           )
    result = requests.get(url, auth=(get_github_token(), 'x-oauth-basic'))
    if result.status_code == 204:
        return True
    else:
        return False


def get_key_fingerprint(key):
    toks = key['key'].split()
    try:
        (enc, key_body, descr) = key['key'].split()
    except ValueError:
        if len(toks) == 2:
            (enc, key_body) = key['key'].split()
        else:
            raise InvalidKey('Invalid key: {}'.format(key['key']))
    if enc not in ['ssh-rsa', 'ssh-dss', 'ssh-ecdsa']:
        raise InvalidKey('Invalid enc type: {}'.format(enc))
    key_bytes = base64.b64decode(key_body)
    md5hash = hashlib.md5()
    md5hash.update(key_bytes)
    fingerprint = md5hash.hexdigest()
    fingerprint = [fingerprint[i: (i + 2)]
                   for i in range(0, len(fingerprint), 2)]
    return ':'.join(fingerprint)


def get_user_keys(user_slug, fingerprints=None):
    """
    Get a users keys from a user name in slug format

    Args:
        user_slug(string): The name of the user in slug format
        fingerprints(list): List of key fingerprints to retrieve

    Returns:
        keys(list): List of keys
    """
    # Ensure that the user name is in slug format for indexing
    forced_user_slug = check_slug_format(user_slug)

    keys = get_paginated_content(
        '{}users/{}/keys'
        .format(API_ENDPOINT, forced_user_slug)
    )
    if fingerprints:
        for key in keys:
            fingerprint = get_key_fingerprint(key)
            if fingerprint not in fingerprints:
                keys.remove(key)
    return keys


def get_user_struct(username, user_data=None):
    user_data = user_data if user_data else {}
    fingerprints = user_data.get('fingerprints', None)
    keys = get_user_keys(username, fingerprints=fingerprints)
    username = user_data.get('unix_username', username)
    fields = ('enc', 'key')
    key_tuples = (key['key'].split(' ') for key in keys)
    key_dict = [dict(zip(fields, map(str, x))) for x in key_tuples]
    # The three lines above can be written in the form:
    # [dict(zip(('enc', 'key'), key.split(' '))) for key in keys]
    # ... but good luck figuring it out in a week from now
    if not key_dict:
        return {}
    return {str(username): {'public_keys': key_dict}}


def handle_string_team(team, org):
    team_users = get_team_members(team, org)
    return team_users, []


def handle_dict_team(team, org):
    team_name = team.keys()[0]
    special_users = team[team_name]
    team_users = get_team_members(team_name, org)
    return team_users, special_users


def get_keys(data):
    out = {}
    for org in data.keys():
        for team in data[org].get('teams', []):
            if isinstance(team, basestring):
                team_users, special_users = handle_string_team(team, org)
            elif isinstance(team, dict):
                team_users, special_users = handle_dict_team(team, org)
            else:
                raise Exception('malformed data for team {}'.format(team))

            for user in special_users:
                user_struct = get_user_struct(*user.items()[0])
                out.update(user_struct)

            for user in team_users:
                if user['login'] in special_users or user['login'] in out:
                    continue
                user_struct = get_user_struct(user['login'])
                out.update(user_struct)

        for user in data[org].get('individuals', []):
            s_user, s_user_data = user.items()[0] \
                if isinstance(user, dict) else (user, {})
            out.update(get_user_struct(s_user, s_user_data))
    return out


def check_slug_format(str):
    """
    Helper function to ensure that a string is in
    a slugged format

    Args:
        str(string): The string to force into a slugged format

    Return:
        str_slug(string): The string in slug format
    """
    # Ensure that the string is in slug format
    str_slug = slugify(str)
    if (str_slug != str):
        logger.warning(
            "Translated string {} into slug {}"
            .format(str, str_slug)
        )
    return str_slug
