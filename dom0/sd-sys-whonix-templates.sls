# -*- coding: utf-8 -*-
# vim: set syntax=yaml ts=2 sw=2 sts=2 et :

##
# Configure apparmor or 'whonix-workstation-17' and 'whonix-gateway-17',
# using upstream Salt formulae to ensure latest Whonix version is installed.
##

include:
  - sd-upgrade-templates
  - qvm.anon-whonix

dom0-enabled-apparmor-on-whonix-gw-template:
  qvm.vm:
    - name: whonix-gateway-17
    - prefs:
      - kernelopts: "nopat apparmor=1 security=apparmor"
    - require:
      - sls: sd-upgrade-templates
      - sls: qvm.anon-whonix


dom0-enabled-apparmor-on-whonix-ws-template:
  qvm.vm:
    - name: whonix-workstation-17
    - prefs:
      - kernelopts: "nopat apparmor=1 security=apparmor"
    - require:
      - sls: sd-upgrade-templates
      - sls: qvm.anon-whonix
