// SPDX-License-Identifier: MIT
// Copyright (C) 2025 V2BX contributors

package adapter

import "net/netip"

type NeighborEntry interface {
	GetDestination() netip.AddrPort
}
