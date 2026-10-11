package hysteria2

import (
	"github.com/sagernet/sing-box/option"
	E "github.com/sagernet/sing/common/exceptions"
	"net"
)

func (h *Inbound) AddUsers(users []option.Hysteria2User, ids []int) error {
	if len(users) != len(ids) {
		return E.New("user IDs and users length mismatch")
	}
	for i, user := range users {
		h.uuidToUid[user.Password] = ids[i]
		h.uidToUuid[ids[i]] = user.Password
		h.userNameList = append(h.userNameList, user.Name)
		h.userPasswords = append(h.userPasswords, user.Password)
	}
	h.updateV2bXUsers()
	return nil
}

func (h *Inbound) DelUsers(names []string) error {
	removed := make(map[string]bool, len(names))
	for _, name := range names {
		removed[name] = true
	}
	userNames := make([]string, 0, len(h.userNameList))
	passwords := make([]string, 0, len(h.userPasswords))
	for i, name := range h.userNameList {
		if removed[name] || removed[h.userPasswords[i]] {
			password := h.userPasswords[i]
			delete(h.uidToUuid, h.uuidToUid[password])
			delete(h.uuidToUid, password)
			h.userconns.Range(func(key, value any) bool {
				if value == name {
					key.(net.Conn).Close()
					h.userconns.Delete(key)
				}
				return true
			})
			continue
		}
		userNames = append(userNames, name)
		passwords = append(passwords, h.userPasswords[i])
	}
	h.userNameList, h.userPasswords = userNames, passwords
	h.updateV2bXUsers()
	return nil
}

func (h *Inbound) updateV2bXUsers() {
	ids := make([]int, len(h.userPasswords))
	for i, password := range h.userPasswords {
		ids[i] = h.uuidToUid[password]
	}
	h.service.UpdateUsers(ids, h.userPasswords)
}
