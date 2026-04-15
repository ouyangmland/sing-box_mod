// SPDX-License-Identifier: MIT
// Copyright (C) 2025 V2BX contributors

package naive

import (
	"context"
	"crypto/tls"

	"github.com/sagernet/sing-box/option"
	"github.com/sagernet/sing/common"
	"github.com/sagernet/sing/common/auth"
)

type Inbound struct {
	tag       string
	users     []auth.User
	server    *uint16
	tlsConfig *tls.Config
}

func NewInbound(ctx context.Context, tag string, options option.NaiveInboundOptions) (*Inbound, error) {
	inbound := &Inbound{tag: tag}
	err := inbound.UpdateUsers(ctx, options)
	if err != nil {
		return nil, err
	}
	return inbound, nil
}

func (n *Inbound) UpdateUsers(ctx context.Context, options option.NaiveInboundOptions) error {
	n.users = nil
	for _, user := range options.Users {
		n.users = append(n.users, auth.User{Username: user.Username, Password: user.Password})
	}
	return nil
}

func (n *Inbound) AddUsers(users []auth.User) error {
	for _, user := range users {
		exists := false
		for i, existing := range n.users {
			if existing.Username == user.Username {
				n.users[i].Password = user.Password
				exists = true
				break
			}
		}
		if !exists {
			n.users = append(n.users, user)
		}
	}
	return nil
}

func (n *Inbound) DelUsers(usernames []string) error {
	for _, username := range usernames {
		for i, user := range n.users {
			if user.Username == username {
				n.users = append(n.users[:i], n.users[i+1:]...)
				break
			}
		}
	}
	return nil
}

func (n *Inbound) SetTLS(config *tls.Config) { n.tlsConfig = config }
func (n *Inbound) SetTLSPort(port uint16)   { n.server = &port }
func (n *Inbound) Type() string             { return common.TypeInbound(n) }
