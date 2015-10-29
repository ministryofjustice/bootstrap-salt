import base64
import hashlib
import os
import requests


API_ENDPOINT = 'https://api.github.com/'
ORG = 'ministryofjustice'


class GithubTokenMissing(Exception):
    pass


class GithubRequestException(Exception):
    pass


class InvalidTeamException(Exception):
    pass


class InvalidKey(Exception):
    pass


def get_github_token():
    if 'GH_TOKEN' not in os.environ:
        raise GithubTokenMissing('GH_TOKEN has not been defined.')
    return os.environ['GH_TOKEN']


def get_paginated_content(url, page=None, out=None, **kwargs):
    if 'auth' not in kwargs:
        kwargs['auth'] = (get_github_token(), 'x-oauth-basic')

    if 'params' in kwargs:
        kwargs['params'].update({'per_page': 100})
    else:
        kwargs['params'] = {'per_page': 100}
    r = requests.get(url, **kwargs)
    if r.status_code != 200:
        raise GithubRequestException('GH API request failed with code: {}'
                                     '\n{}'.format(r.status_code, r.text))

    if not out:
        out = r.json()
    else:
        out.extend(r.json())

    if 'next' in r.links:
        return get_paginated_content(r.links['next']['url'], out=out, **kwargs)
    else:
        return out


def get_teams(org=ORG):
    url = '{}orgs/{}/teams'.format(API_ENDPOINT, org)
    response = get_paginated_content(url)
    return response


def get_org_members(org=ORG):
    url = '{}orgs/{}/members'.format(org)
    return get_paginated_content(url)


def get_org_team(team_slug, org=ORG):
    teams = get_teams(org)
    team = filter(lambda x: x['slug'] == team_slug, teams)
    if len(team) == 0:
        raise InvalidTeamException(
            'Team {} is not part of org {}'.format(team_slug, org))
    else:
        return team[0]


def get_team_members(team_slug, org=ORG):
    try:
        team = get_org_team(team_slug, org)
    except InvalidTeamException:
        return {}
    url = '{}teams/{}/members'.format(API_ENDPOINT, team['id'])
    return get_paginated_content(url)


def check_org_membership(org, user):
    url = '{}orgs/{}/members/{}'.format(API_ENDPOINT, org, user)
    r = requests.get(url, auth=(get_github_token(), 'x-oauth-basic'))
    if r.status_code == 204:
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
    fingerprint = [fingerprint[i: (i + 2)] for i in range(0, len(fingerprint), 2)]
    return ':'.join(fingerprint)


def get_user_keys(user, fingerprints=None):
    keys = get_paginated_content('{}users/{}/keys'.format(API_ENDPOINT, user))
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


if __name__ == '__main__':
    data = {
        'ministryofjustice': {
            'individuals': [
                {
                    'koikonom': {
                        'fingerprints':
                            ['35:53:6f:27:fe:39:8b:d8:dd:87:19:f3:40:d2:84:6a'],
                        'unix_username': 'kyriakos'
                    }
                }, {
                    'ashb': {
                        'fingerprints':
                            ['0c:11:2b:78:ff:8d:5f:f0:dc:27:8e:e2:f8:2f:ab:25',
                             'af:e0:6c:dc:bd:9b:bf:1d:9b:de:2d:de:12:6e:f2:8a',
                             ]
                    }
                },
                'mattmb'
            ],
            'teams': [
                {
                    'prison-visits-booking': [
                        {
                            'jasiek': {
                                'unix_username': 'jan',
                                'fingerprint': '00:11:22:33'
                            }
                        }
                    ]
                },
                'civil-claims'
            ]
        }
    }
    # print yaml.dump(get_keys(data), default_flow_style=False)
    print get_keys(data)
