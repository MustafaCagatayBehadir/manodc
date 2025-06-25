*** Settings ***
Documentation       manodc services robot tests

Resource            ../../robot-library/keywords.robot
Library             ../../robot-library/manage_suite.py
Library             ../../robot-library/manage_test.py

Test Teardown       Delete Service  ${SERVICE}  ${INSTANCE}


*** Variables ***
${write}        false
${diff}         false
${SERVICE}      bridge-domains bridge-domain-vlan
${PLAN}         bridge-domains bridge-domain-vlan-data
${INSTANCE}     ${EMPTY}
# TDIR set for keywords.robot
${TDIR}         ${CURDIR}


*** Test Cases ***
BD VLAN DEFINITION
  [Documentation]       BD VLAN DEFINITION
  ...                   Layer 2 vlan definition at switches
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD VLAN DESCRIPTION
  [Documentation]       BD VLAN DESCRIPTION
  ...                   Layer 2 vlan description
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD ACCESS VLAN
  [Documentation]       BD ACCESS VLAN
  ...                   Layer 2 access vlan definition
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD ACCESS VLAN STORM CONTROL
  [Documentation]       BD ACCESS VLAN STORM CONTROL
  ...                   Layer 2 access vlan definition with storm control
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD TRUNK VLAN
  [Documentation]       BD TRUNK VLAN
  ...                   Layer 2 trunk vlan definition
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD NATIVE VLAN
  [Documentation]       BD NATIVE VLAN
  ...                   Layer 2 native vlan definition
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD VLAN LAYER3
  [Documentation]       BD VLAN LAYER3
  ...                   Layer 3 access vlan definition
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}

BD VLAN LAYER3 DESCRIPTION
  [Documentation]       BD VLAN LAYER3 DESCRIPTION
  ...                   Layer 3 vlan description
  set global variable   ${INSTANCE}   AVR-NDC1-CONTROL Mavenir-vIMS 1000
  Reactive case         ${INSTANCE}