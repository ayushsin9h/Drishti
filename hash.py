"""Generate a bcrypt hash for a password, to paste into auth_config.yaml.

Usage:
    python hash.py
    > Password to hash: ********
    <prints the hash>

Then replace the plain-text `password:` value in auth_config.yaml with the hash.
"""
import getpass

import streamlit_authenticator as stauth

if __name__ == "__main__":
    pw = getpass.getpass("Password to hash: ")
    try:
        hashed = stauth.Hasher([pw]).generate()[0]      # older API
    except Exception:
        hashed = stauth.Hasher.hash(pw)                 # newer API
    print(hashed)
