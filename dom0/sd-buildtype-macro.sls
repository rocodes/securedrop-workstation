# -*- coding: utf-8 -*-
# vim: set syntax=yaml ts=2 sw=2 sts=2 et :

##
# sd-buildtype
# =====================
# A macro to set a Qubes feature (qvm-features) indicating the VM build type (dev, staging, prod).
# This value can be read using `qubesdb-read /sd-buildtype` from the target VM.

{% macro set_buildtype(vm_name, environment) %}

{{ vm_name }}-add-sd-buildtype-feature:
  qvm.features:
    - name: {{ vm_name }}
    - set:
      - sd-buildtype: {{ environment }}

{% endmacro %}