#!/usr/bin/env python3
"""Apply only V2bX live-user hooks to current upstream QUIC inbounds."""
from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one occurrence of {old!r}, found {text.count(old)}")
    return text.replace(old, new, 1)


for proto in ("hysteria2", "tuic"):
    path = Path("protocol") / proto / "inbound.go"
    text = path.read_text()
    if "func (h *Inbound) NewConnectionEx(" not in text:
        raise RuntimeError(f"{path}: current sing-quic handler API not found")
    if "userconns sync.Map" in text:
        raise RuntimeError(f"{path}: V2bX extension already present")
    text = replace_once(text, '"net"', '"net"\n\t"sync"')
    text = replace_once(
        text,
        "\tuserNameList []string\n}",
        "\tuserNameList []string\n\tuserPasswords []string\n\tuserUUIDs []string\n\tuuidToUid map[string]int\n\tuidToUuid map[int]string\n\tuserconns sync.Map\n}",
    )
    key_field = "Password" if proto == "hysteria2" else "UUID"
    init = (
        "\tinbound.uuidToUid = make(map[string]int, len(options.Users))\n"
        "\tinbound.uidToUuid = make(map[int]string, len(options.Users))\n"
        "\tfor index, user := range options.Users {\n"
        f"\t\tinbound.uuidToUid[user.{key_field}] = index\n"
        f"\t\tinbound.uidToUuid[index] = user.{key_field}\n"
        "\t}\n"
        "\tinbound.userPasswords = append([]string(nil), userPasswordList...)\n"
    )
    if proto == "tuic":
        init += "\tfor _, user := range options.Users { inbound.userUUIDs = append(inbound.userUUIDs, user.UUID) }\n"
    text = replace_once(text, "\treturn inbound, nil", init + "\treturn inbound, nil")
    text = replace_once(
        text,
        "\th.router.RouteConnectionEx(ctx, conn, metadata, onClose)",
        "\th.userconns.Store(conn, metadata.User)\n"
        "\tdefer h.userconns.Delete(conn)\n"
        "\th.router.RouteConnectionEx(ctx, conn, metadata, onClose)",
    )
    path.write_text(text)

    extension = Path("protocol") / proto / f"{proto}_user.go"
    if proto == "hysteria2":
        extension.write_text('''package hysteria2

import (
    "net"
    "github.com/sagernet/sing-box/option"
    E "github.com/sagernet/sing/common/exceptions"
)

func (h *Inbound) AddUsers(users []option.Hysteria2User, ids []int) error {
    if len(users) != len(ids) { return E.New("user IDs and users length mismatch") }
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
    for _, name := range names { removed[name] = true }
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
    for i, password := range h.userPasswords { ids[i] = h.uuidToUid[password] }
    h.service.UpdateUsers(ids, h.userPasswords)
}
''')
    else:
        extension.write_text('''package tuic

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
''')
    print(f"Patched {path} and wrote {extension}")
