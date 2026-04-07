package naive

import (
	"github.com/sagernet/sing/common/auth"
)

func (h *Inbound) AddUsers(users []auth.User) error {
	h.options.Users = append(h.options.Users, users...)
	h.authenticator = auth.NewAuthenticator(h.options.Users)
	return nil
}

func (h *Inbound) DelUsers(names []string) error {
	nameMap := make(map[string]struct{}, len(names))
	for _, name := range names {
		nameMap[name] = struct{}{}
	}
	filteredUsers := make([]auth.User, 0, len(h.options.Users))
	for _, user := range h.options.Users {
		if _, found := nameMap[user.Username]; !found {
			filteredUsers = append(filteredUsers, user)
		}
	}
	h.options.Users = filteredUsers
	h.authenticator = auth.NewAuthenticator(h.options.Users)
	return nil
}
