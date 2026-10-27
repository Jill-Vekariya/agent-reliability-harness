"""Keep the compromised emSign G3 trust anchor out of the bundled CA store."""

import hashlib
import re
import ssl

import certifi


def test_compromised_emsign_root_is_not_in_certifi_bundle():
    # GHSA-6q48-6c7w-9gw2; compare certificate bytes, not a version string.
    compromised = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
    certificates = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", certifi.contents(), re.S
    )
    assert certificates, "The CA bundle must contain certificates"
    fingerprints = {
        hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() for pem in certificates
    }
    assert compromised not in fingerprints
