## Model Tree
```
module: manodc
  +--rw manodc-actions
  +--rw dc-sites
  |  +--rw dc-site* [location hall fabric]
  |     +--rw location           string
  |     +--rw hall               string
  |     +--rw fabric             fabric-name
  |     +--rw site-name?         string
  |     +--rw (topology)?
  |     |  +--:(clos)
  |     |  |  +--rw eor* [name]
  |     |  |  |  +--rw name    -> /ncs:devices/device/name
  |     |  |  |  +--rw role    eor-role
  |     |  |  +--rw tor* [name]
  |     |  |  |  +--rw name    -> /ncs:devices/device/name
  |     |  |  +--rw tor-group* [name]
  |     |  |     +--rw name     string
  |     |  |     +--rw tor-1    -> /ncs:devices/device/name
  |     |  |     +--rw tor-2    -> /ncs:devices/device/name
  |     |  +--:(flat)
  |     |     +--rw switch* [name]
  |     |        +--rw name    -> /ncs:devices/device/name
  |     +--rw resource-pools
  |        +--rw vlan-id-pool      -> /ralloc:resource-pools/idalloc:id-pool/name
  |        +--rw vrrpv3-id-pool    -> /ralloc:resource-pools/idalloc:id-pool/name
  +--rw bridge-domains
     +--ro bridge-domain-vlan-data* [site name vlan]
     |  +--ro site    string
     |  +--ro name    string
     |  +--ro vlan    uint16
     +--rw bridge-domain-vlan* [site name vlan]
     |  +--rw site           -> /dc-sites/dc-site/site-name
     |  +--rw name           string
     |  +--rw vlan           vlan-id
     |  +--rw description?   string
     |  +--rw switch* [name]
     |  |  +--rw name           -> /ncs:devices/device/name
     |  |  +--rw switch-type?   switch-type
     |  |  +--rw port* [id]
     |  |     +--rw id                tor-port
     |  |     +--rw connected-host    string
     |  |     +--rw host-port         string
     |  |     +--rw mode?             vlan-mode
     |  |     +--rw storm-control?    boolean
     |  +--rw layer3!
     |     +--rw vrf?       string
     |     +--rw gateway    tailf:ip-address-and-prefix-length
     +--ro bridge-domain-vlan-switch-data* [site name vlan switch]
     |  +--ro site      string
     |  +--ro name      string
     |  +--ro vlan      uint16
     |  +--ro switch    string
     +--rw bridge-domain-vlan-switch* [site name vlan switch]
        +--rw site           -> /dc-sites/dc-site/site-name
        +--rw name           string
        +--rw vlan           vlan-id
        +--rw switch         -> /ncs:devices/device/name
        +--rw description?   string
        +--rw port* [id]
        |  +--rw id                tor-port
        |  +--rw connected-host?   string
        |  +--rw host-port?        string
        |  +--rw mode?             vlan-mode
        |  +--rw storm-control?    boolean
        +--rw layer3!
           +--rw vrf?               string
           +--rw address            tailf:ip-address-and-prefix-length
           +--rw vip-address?       tailf:ip-address-and-prefix-length
           +--rw vrrpv3-id?         uint8
           +--rw vrrpv3-priority?   uint8

```
