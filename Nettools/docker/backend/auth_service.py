"""
NetTools - Authentication

Optional login (off by default) with three methods that can be combined:

  * local  : one username / password stored hashed (PBKDF2-SHA256)
  * ldap   : any LDAP server (LLDAP, OpenLDAP, Active Directory...). Either a
             service account searches the user (bind DN + filter) or the user
             DN is built from a template; then the user's password is checked
             with a bind. Optional required group.
  * oidc   : any OpenID Connect provider (Authelia, Authentik, Keycloak...),
             authorization code flow with PKCE. Optional required group
             (from the 'groups' claim).

Sessions are random tokens in an HttpOnly cookie; only their SHA-256 is
stored. Emergency switch: NETTOOLS_AUTH_DISABLED=true disables the login.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

COOKIE = 'nettools_session'
PBKDF2_ITERATIONS = 240000
DEFAULT_LDAP_FILTER = '(&(objectClass=person)(uid={username}))'

# ---------- helpers ----------

def auth_disabled_by_env() -> bool:
    return os.environ.get('NETTOOLS_AUTH_DISABLED', '').lower() in ('1', 'true', 'yes')


def is_enabled(settings: dict) -> bool:
    return bool(settings.get('auth_enabled')) and not auth_disabled_by_env()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split('$')
        assert algo == 'pbkdf2_sha256'
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def methods(settings: dict) -> dict:
    """Which login methods are usable with the current settings."""
    local = bool(settings.get('auth_local_enabled')) and bool(settings.get('auth_local_password_hash'))
    ldap = bool(settings.get('auth_ldap_enabled')) and bool(settings.get('auth_ldap_url')) and \
        bool(settings.get('auth_ldap_base_dn') or settings.get('auth_ldap_user_dn_template'))
    oidc = bool(settings.get('auth_oidc_enabled')) and bool(settings.get('auth_oidc_issuer')) and \
        bool(settings.get('auth_oidc_client_id'))
    return {'local': local, 'ldap': ldap, 'oidc': oidc,
            'oidc_name': settings.get('auth_oidc_name') or 'SSO'}


# ---------- brute force protection ----------
_failures = {}  # ip -> [timestamps]
MAX_FAILURES, WINDOW = 5, 300


def too_many_failures(ip: str) -> bool:
    now = time.time()
    _failures[ip] = [t for t in _failures.get(ip, []) if now - t < WINDOW]
    return len(_failures[ip]) >= MAX_FAILURES


def record_failure(ip: str):
    _failures.setdefault(ip, []).append(time.time())


def clear_failures(ip: str):
    _failures.pop(ip, None)


# ---------- local ----------

def check_local(settings: dict, username: str, password: str) -> dict:
    if not settings.get('auth_local_enabled') or not settings.get('auth_local_password_hash'):
        return None
    if (username or '').strip().lower() != (settings.get('auth_local_username') or 'admin').strip().lower():
        return None
    if verify_password(password, settings['auth_local_password_hash']):
        return {'username': settings.get('auth_local_username') or 'admin', 'method': 'local'}
    return None


# ---------- LDAP ----------

class AuthError(Exception):
    pass


def _group_matches(member_of: list, group: str) -> bool:
    g = group.strip().lower()
    for dn in member_of or []:
        d = str(dn).strip().lower()
        if d == g or d.startswith(f'cn={g},'):
            return True
    return False


def check_ldap(settings: dict, username: str, password: str, raise_errors: bool = False) -> dict:
    """Returns {'username', 'method', 'groups'} or None. With raise_errors
    the reason of the failure is raised (used by the settings test)."""
    try:
        from ldap3 import Server, Connection, Tls, SUBTREE, NONE
        from ldap3.utils.conv import escape_filter_chars
        import ssl
    except ImportError:
        if raise_errors:
            raise AuthError("La libreria ldap3 no esta instalada")
        return None
    if not username or not password:
        if raise_errors:
            raise AuthError("Usuario y contrasena obligatorios")
        return None

    url = settings.get('auth_ldap_url') or ''
    verify = bool(settings.get('auth_ldap_verify_ssl'))
    tls = Tls(validate=ssl.CERT_REQUIRED if verify else ssl.CERT_NONE)
    # get_info=NONE + check_names=False: request optional attributes (displayName,
    # jpegPhoto...) even if the server schema does not have them
    server = Server(url, use_ssl=url.lower().startswith('ldaps://'), tls=tls, connect_timeout=6, get_info=NONE)
    base = settings.get('auth_ldap_base_dn') or ''
    bind_dn = settings.get('auth_ldap_bind_dn') or ''
    template = settings.get('auth_ldap_user_dn_template') or ''
    group = (settings.get('auth_ldap_group') or '').strip()
    uname = escape_filter_chars(username.strip())

    def fail(msg):
        if raise_errors:
            raise AuthError(msg)
        return None

    try:
        user_dn, member_of, profile = None, [], {}
        if bind_dn:
            svc = Connection(server, bind_dn, settings.get('auth_ldap_bind_password') or '',
                             auto_bind=True, receive_timeout=8, check_names=False)
            flt = (settings.get('auth_ldap_user_filter') or DEFAULT_LDAP_FILTER).replace('{username}', uname)
            svc.search(base, flt, SUBTREE, attributes=['memberOf', 'cn', 'displayName', 'jpegPhoto'])
            if not svc.entries:
                svc.unbind()
                return fail("Usuario no encontrado en LDAP")
            entry = svc.entries[0]
            user_dn = entry.entry_dn
            member_of = list(entry.memberOf.values) if 'memberOf' in entry.entry_attributes else []
            profile = _ldap_profile(entry)
            if group and not member_of:
                # servers without memberOf: look for the group itself
                svc.search(base, f"(&(cn={escape_filter_chars(group)})"
                                 f"(|(member={escape_filter_chars(user_dn)})(uniqueMember={escape_filter_chars(user_dn)})))",
                           SUBTREE, attributes=['cn'])
                if svc.entries:
                    member_of = [f"cn={group},"]
            svc.unbind()
        elif template:
            user_dn = template.replace('{username}', uname)
        else:
            return fail("Configura un usuario de servicio (bind DN) o una plantilla de DN de usuario")

        conn = Connection(server, user_dn, password, receive_timeout=8, check_names=False)
        if not conn.bind():
            return fail("Contrasena incorrecta")
        if not bind_dn:
            # read our own groups with the user's credentials
            try:
                conn.search(user_dn, '(objectClass=*)', 'BASE', attributes=['memberOf', 'cn', 'displayName', 'jpegPhoto'])
                if conn.entries:
                    if 'memberOf' in conn.entries[0].entry_attributes:
                        member_of = list(conn.entries[0].memberOf.values)
                    profile = _ldap_profile(conn.entries[0])
            except Exception:
                pass
        conn.unbind()
        if group and not _group_matches(member_of, group):
            return fail(f"El usuario no pertenece al grupo '{group}'")
        groups = [str(g).split(',')[0].split('=', 1)[-1] for g in member_of]
        return {'username': username.strip(), 'method': 'ldap', 'groups': groups,
                'name': profile.get('name') or username.strip(), 'avatar': profile.get('avatar')}
    except AuthError:
        raise
    except Exception as e:
        logger.warning(f"LDAP login error: {e}")
        return fail(f"Error de LDAP: {e}")


def _ldap_profile(entry) -> dict:
    """Display name and photo (jpegPhoto, e.g. the LLDAP avatar) as a data URL."""
    out = {}
    attrs = entry.entry_attributes
    for a in ('displayName', 'cn'):
        if a in attrs and entry[a].value:
            v = entry[a].value
            out['name'] = v[0] if isinstance(v, list) else str(v)
            break
    if 'jpegPhoto' in attrs and entry['jpegPhoto'].raw_values:
        raw = entry['jpegPhoto'].raw_values[0]
        if raw and len(raw) <= 300 * 1024:
            mime = 'image/png' if raw[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
            out['avatar'] = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    return out


# ---------- OpenID Connect ----------
_discovery_cache = {}


def discovery(settings: dict) -> dict:
    issuer = (settings.get('auth_oidc_issuer') or '').rstrip('/')
    if not issuer:
        raise AuthError("Falta la URL del proveedor (issuer)")
    cached = _discovery_cache.get(issuer)
    if cached and time.time() - cached[0] < 3600:
        return cached[1]
    try:
        r = requests.get(f"{issuer}/.well-known/openid-configuration", timeout=8,
                         verify=settings.get('auth_oidc_verify_ssl', True) is not False)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise AuthError(f"No se pudo leer la configuracion OIDC de {issuer}: {e}")
    for k in ('authorization_endpoint', 'token_endpoint'):
        if not data.get(k):
            raise AuthError(f"El proveedor no publica {k}")
    _discovery_cache[issuer] = (time.time(), data)
    return data


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def oidc_start(settings: dict, redirect_uri: str) -> tuple:
    """Returns (authorization_url, state, verifier, nonce)."""
    d = discovery(settings)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    params = {
        'response_type': 'code',
        'client_id': settings.get('auth_oidc_client_id'),
        'redirect_uri': redirect_uri,
        'scope': settings.get('auth_oidc_scopes') or 'openid profile email groups',
        'state': state,
        'nonce': nonce,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return f"{d['authorization_endpoint']}?{urlencode(params)}", state, verifier, nonce


def _jwt_payload(token: str) -> dict:
    try:
        part = token.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    except Exception:
        return {}


def oidc_finish(settings: dict, code: str, redirect_uri: str, verifier: str, nonce: str) -> dict:
    d = discovery(settings)
    verify = settings.get('auth_oidc_verify_ssl', True) is not False
    client_id = settings.get('auth_oidc_client_id')
    secret = settings.get('auth_oidc_client_secret') or ''
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri,
            'code_verifier': verifier}
    auth = (client_id, secret) if secret else None
    if not secret:
        data['client_id'] = client_id
    try:
        r = requests.post(d['token_endpoint'], data=data, auth=auth, timeout=10, verify=verify,
                          headers={'Accept': 'application/json'})
    except Exception as e:
        raise AuthError(f"No se pudo contactar con el proveedor: {e}")
    if r.status_code != 200:
        raise AuthError(f"El proveedor rechazo el codigo (HTTP {r.status_code}): {r.text[:200]}")
    tokens = r.json()
    claims = _jwt_payload(tokens.get('id_token', ''))
    # The token comes straight from the provider over TLS (confidential client);
    # still check that it was issued for us and for this login.
    if claims:
        aud = claims.get('aud')
        if (isinstance(aud, list) and client_id not in aud) or (isinstance(aud, str) and aud != client_id):
            raise AuthError("El token no es para este cliente")
        if nonce and claims.get('nonce') and claims.get('nonce') != nonce:
            raise AuthError("Nonce no valido")
    if d.get('userinfo_endpoint') and tokens.get('access_token'):
        try:
            u = requests.get(d['userinfo_endpoint'], timeout=10, verify=verify,
                             headers={'Authorization': f"Bearer {tokens['access_token']}"})
            if u.status_code == 200:
                claims = {**claims, **u.json()}
        except Exception as e:
            logger.warning(f"OIDC userinfo failed: {e}")
    username = claims.get('preferred_username') or claims.get('email') or claims.get('sub')
    if not username:
        raise AuthError("El proveedor no devolvio el usuario")
    groups = claims.get('groups') or []
    if isinstance(groups, str):
        groups = [groups]
    required = (settings.get('auth_oidc_group') or '').strip()
    if required and required.lower() not in [str(g).lower() for g in groups]:
        raise AuthError(f"El usuario {username} no pertenece al grupo '{required}'")
    picture = claims.get('picture') if str(claims.get('picture') or '').startswith(('https://', 'data:image/')) else None
    return {'username': username, 'method': 'oidc', 'groups': groups,
            'name': claims.get('name') or username, 'avatar': picture}
