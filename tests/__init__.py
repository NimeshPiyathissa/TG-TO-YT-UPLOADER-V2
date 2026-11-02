# Makes tests a package so pytest puts the repo root first on sys.path. tgcrypto installs its own top-level
# "tests" package into site-packages, which would otherwise shadow this folder.
