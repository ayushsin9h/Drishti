"""OPTIONAL login wrapper (streamlit-authenticator).

This is NOT wired into app.py by default, so the core demo always runs. To turn
it on, add these two lines at the top of app.py (right after the imports):

    from src.auth import require_login
    name, username, roles = require_login()

Security notes:
  * Passwords are bcrypt-hashed by the library (auto_hash=True). For real
    security, pre-hash with `python hash.py` and store ONLY the hash in
    auth_config.yaml — never commit plain-text passwords to a public repo.
  * The login version's `login()` signature has changed across releases; this
    reads auth state from st.session_state (the stable pattern). Pin your
    installed version and test the flow locally.
"""
import yaml
from yaml.loader import SafeLoader

import streamlit as st
import streamlit_authenticator as stauth


def get_authenticator(path="auth_config.yaml"):
    with open(path) as f:
        config = yaml.load(f, Loader=SafeLoader)
    return stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
        auto_hash=True,
    )


def require_login(path="auth_config.yaml"):
    """Render the login widget; stop the app unless the user is authenticated.

    Returns (name, username, roles) once logged in.
    """
    authenticator = get_authenticator(path)
    authenticator.login(location="main")

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Invalid username or password.")
        st.stop()
    if status is None:
        st.info("Please log in to continue.")
        st.stop()

    authenticator.logout("Logout", "sidebar")
    return (st.session_state.get("name"),
            st.session_state.get("username"),
            st.session_state.get("roles") or [])
