# Official packages

The four supplied final builds use release 1.0.28 (DEB: 1.0.28-dreamos).

| Receiver | OPKG image | DPKG image |
| --- | --- | --- |
| Ordinary receivers, including DM900/DM920 | Ultra_Audio_Final_V1.ipk | Ultra_Audio_Final_DreamOS.deb |
| Dreambox One / Two | Ultra_Audio_Dreambox_One_Two.ipk | Ultra_Audio_Dreambox_One_Two.deb |

Each variant has its own manifest. A missing One/Two update never falls back to an ordinary build. The updater checks the family, exact filename, format, version, SHA256 and package control family before installation.

`python3 -B scripts/unpack_sources.py` recovers all four source trees. Never replace a One/Two source tree with an ordinary build when preparing future releases.
