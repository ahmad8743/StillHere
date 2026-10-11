"""Server-only renewal wrapper, fixed-label failures and hook retry after failure."""
import os
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    os.umask(0o077)
    try:
        subprocess.run(["/opt/certbot/bin/certbot", "renew", "--cert-name", "stillhere-ip", "--quiet", "--no-directory-hooks"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        # Also reconciles a newly issued pair if an earlier hook/reload failed.
        subprocess.run(["/usr/bin/python3", "/opt/stillhere/current/deploy/tls_publish.py"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    except Exception:
        sys.exit("tls_renewal_failed")
    print("tls_renewal_ok")
