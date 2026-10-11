package tuic

import (
    "net"
    "github.com/gofrs/uuid/v5"
    "github.com/sagernet/sing-box/option"
    E "github.com/sagernet/sing/common/exceptions"
)

func (h *Inbound) AddUsers(users []option.TUICUser, ids []int) error {
    if len(users) != len(ids) { return E.New("user IDs and users length mismatch") }
    for i, user := range users {
        if _, err := uuid.FromString(user.UUID); err != nil { return E.Cause(err, "invalid uuid for user ", i) }
        h.uuidToUid[user.UUID] = ids[i]
        h.uidToUuid[ids[i]] = user.UUID
        h.userNameList = append(h.userNameList, user.Name)
        h.userPasswords = append(h.userPasswords, user.Password)
        h.userUUIDs = append(h.userUUIDs, user.UUID)
    }
    return h.updateV2bXUsers()
}

func (h *Inbound) DelUsers(names []string) error {
    removed := make(map[string]bool, len(names))
    for _, name := range names { removed[name] = true }
    userNames := make([]string, 0, len(h.userNameList))
    passwords := make([]string, 0, len(h.userPasswords))
    remainingUUIDs := make([]string, 0, len(h.userNameList))
    for i, name := range h.userNameList {
        userUUID := h.userUUIDs[i]
        if removed[name] || removed[userUUID] {
            delete(h.uidToUuid, h.uuidToUid[userUUID])
            delete(h.uuidToUid, userUUID)
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
        remainingUUIDs = append(remainingUUIDs, userUUID)
    }
    h.userNameList, h.userPasswords, h.userUUIDs = userNames, passwords, remainingUUIDs
    return h.updateV2bXUsers()
}

func (h *Inbound) updateV2bXUsers() error {
    ids := make([]int, 0, len(h.userUUIDs))
    uuids := make([][16]byte, 0, len(h.userUUIDs))
    for _, userUUID := range h.userUUIDs {
        parsed, err := uuid.FromString(userUUID)
        if err != nil { return err }
        ids = append(ids, h.uuidToUid[userUUID])
        uuids = append(uuids, parsed)
    }
    h.server.UpdateUsers(ids, uuids, h.userPasswords)
    return nil
}
