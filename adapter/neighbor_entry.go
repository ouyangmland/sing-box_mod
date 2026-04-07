package adapter

import (
	"net/netip"
)

type NeighborEntry interface {
	GetDestination() netip.AddrPort
}
