"""
Synapse — The Neural Bridge for University Clubs
=================================================
Connects Discord engagement to GitHub contributions through a gamified XP
system.  Fork this repo, edit ``config.yaml``, and you're up and running.

Package layout::

    synapse/
    ├── config.py          # YAML → typed Python config
    ├── database/
    │   ├── engine.py      # SQLAlchemy engine + async helper
    │   └── models.py      # User, Quest, ActivityLog tables
    ├── bot/
    │   ├── core.py        # Bot subclass, cog loader
    │   └── cogs/
    │       ├── social.py  # on_message XP engine
    │       └── meta.py    # /link-github, /profile commands
    └── dashboard/
        └── app.py         # Streamlit admin interface
"""

__version__ = "0.1.0"
