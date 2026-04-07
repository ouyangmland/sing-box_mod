#!/usr/bin/env python3
"""
Sync sing-box upstream releases to V2BX tags.
Downloads official sing-box release, applies V2BX patches, tags and pushes.

Usage: python3 sync_upstream.py [--force]
"""
import os
import sys
import json
import subprocess
import urllib.request
import argparse
import re

GITHUB_REPO = "SagerNet/sing-box"
MOD_REPO = "ouyangmland/sing-box_mod"
V2BX_BRANCH = "v2bx-stable"
WORKDIR = os.environ.get("GITHUB_WORKSPACE", "/tmp/sync-upstream")


def ghgraphql(query: str, variables: dict = None) -> dict:
    """Make a GitHub GraphQL API call."""
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def ghapi(url: str, headers: dict = None) -> dict:
    """Make a GitHub REST API call."""
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", "")
    req_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def run(cmd: list, cwd: str = None, check=True, capture=True) -> subprocess.CompletedProcess:
    """Run a shell command."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
    )
    if result.stdout:
        print(result.stdout[:500])
    if result.stderr:
        print(result.stderr[:500], file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def get_latest_upstream_tag() -> str:
    """Get latest stable tag from SagerNet/sing-box."""
    data = ghapi("https://api.github.com/repos/SagerNet/sing-box/releases/latest")
    tag = data["tag_name"]
    print(f"Latest upstream tag: {tag}")
    return tag


def check_tag_exists(tag: str) -> bool:
    """Check if a tag exists in the mod repo."""
    try:
        ghapi(f"https://api.github.com/repos/{MOD_REPO}/git/refs/tags/{tag}")
        return True
    except Exception:
        return False


def parse_version(tag: str) -> tuple:
    """Parse 'v1.13.6' into (1, 13, 6)."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        raise ValueError(f"Cannot parse version from tag: {tag}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def get_current_base_version() -> str | None:
    """Get the sing-box version our current v2bx-stable is based on."""
    try:
        # Check the go.mod in v2bx-stable branch
        data = ghapi(f"https://api.github.com/repos/{MOD_REPO}/contents/go.mod?ref={V2BX_BRANCH}")
        import base64
        content = base64.b64decode(data["content"]).decode()
        # Look for github.com/sagernet/sing-box vX.Y.Z
        m = re.search(r"github\.com/SagerNet/sing-box v(\d+\.\d+\.\d+)", content)
        if m:
            return f"v{m.group(1)}"
    except Exception as e:
        print(f"Could not determine current base version: {e}")
    return None


def download_official_release(tag: str, dest: str) -> str:
    """Download and extract official sing-box release tarball."""
    os.makedirs(dest, exist_ok=True)
    tarball = f"/tmp/sing-box-{tag}.tar.gz"

    url = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.tar.gz"
    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, tarball)

    # Extract
    run(["tar", "-xzf", tarball, "-C", dest, "--strip-components=1"], cwd=dest)
    os.remove(tarball)

    # List key files
    for f in ["go.mod", "adapter/router.go", "route/router.go"]:
        path = os.path.join(dest, f)
        if os.path.exists(path):
            print(f"  {f}: {os.path.getsize(path)} bytes")
    return dest


def get_v2bx_patch_info() -> dict:
    """Return dict of files that need V2BX patches."""
    return {
        "third_party/sagernet/sing-vmess": "dir",
        "protocol/vmess/vmess_user.go": "file",
        "protocol/vless/vless_user.go": "file",
        "protocol/trojan/trojan_user.go": "file",
        "protocol/shadowsocks/shadowsocks_user.go": "file",
        "protocol/tuic/tuic_user.go": "file",
        "protocol/hysteria/hysteria_user.go": "file",
        "protocol/hysteria2/hysteria2_user.go": "file",
        "protocol/anytls/anytls_user.go": "file",
        "protocol/naive/naive_user.go": "file",
        "protocol/trojan/inbound.go": "file",
        "protocol/vless/inbound.go": "file",
        "protocol/tuic/inbound.go": "file",
        "protocol/hysteria2/inbound.go": "file",
        "protocol/anytls/inbound.go": "file",
        "protocol/shadowsocks/inbound.go": "file",
        "protocol/hysteria/inbound.go": "file",
        "adapter/neighbor_entry.go": "file",
        "option/dns.go": "file",
        "outbound.go": "file",
        "tailscale.go": "file",
        "transport/trojan/protocol.go": "file",
    }


def fetch_moeclub_v2bx_files(tag: str, dest: str):
    """Fetch v1.13.1-beta.2-v2bx.2 files from MoeclubM for reference."""
    moe_tag = "v1.13.1-beta.2-v2bx.2"
    base_url = f"https://raw.githubusercontent.com/MoeclubM/sing-box_mod/{moe_tag}"
    moe_dir = os.path.join(dest, "_moeclub")
    os.makedirs(moe_dir, exist_ok=True)

    files = [
        "go.mod", "go.sum",
        "third_party/sagernet/sing-vmess/connection.go",
        "third_party/sagernet/sing-vmess/aead.go",
        "protocol/vmess/vmess_user.go",
        "protocol/vless/vless_user.go",
        "protocol/trojan/trojan_user.go",
        "protocol/shadowsocks/shadowsocks_user.go",
        "protocol/tuic/tuic_user.go",
        "protocol/hysteria/hysteria_user.go",
        "protocol/hysteria2/hysteria2_user.go",
        "protocol/anytls/anytls_user.go",
        "protocol/trojan/inbound.go",
        "protocol/vless/inbound.go",
        "protocol/tuic/inbound.go",
        "protocol/hysteria2/inbound.go",
        "protocol/anytls/inbound.go",
        "protocol/shadowsocks/inbound.go",
        "protocol/hysteria/inbound.go",
        "option/dns.go",
        "outbound.go",
        "tailscale.go",
        "transport/trojan/protocol.go",
    ]

    for f in files:
        url = f"{base_url}/{f}"
        local_path = os.path.join(moe_dir, f)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        try:
            urllib.request.urlretrieve(url, local_path)
            print(f"  Fetched: {f}")
        except Exception as e:
            print(f"  Failed to fetch {f}: {e}")


def patch_upstream(upstream_dir: str, moeclub_dir: str):
    """Apply V2BX patches to the upstream sing-box source."""
    print("Applying V2BX patches...")

    # 1. Copy third_party/sagernet/sing-vmess
    src_vmess = os.path.join(moeclub_dir, "third_party/sagernet/sing-vmess")
    dst_vmess = os.path.join(upstream_dir, "third_party/sagernet/sing-vmess")
    if os.path.exists(src_vmess):
        import shutil
        if os.path.exists(dst_vmess):
            shutil.rmtree(dst_vmess)
        shutil.copytree(src_vmess, dst_vmess)
        print("  Copied third_party/sagernet/sing-vmess")

    # 2. Copy *_user.go files
    protocols = ["vmess", "vless", "trojan", "shadowsocks", "tuic", "hysteria", "hysteria2", "anytls"]
    for proto in protocols:
        src_user = os.path.join(moeclub_dir, f"protocol/{proto}/{proto}_user.go")
        src_inbound = os.path.join(moeclub_dir, f"protocol/{proto}/inbound.go")
        dst_proto = os.path.join(upstream_dir, f"protocol/{proto}")
        os.makedirs(dst_proto, exist_ok=True)

        if os.path.exists(src_user):
            shutil.copy2(src_user, os.path.join(dst_proto, f"{proto}_user.go"))
            print(f"  Copied {proto}_user.go")

        if os.path.exists(src_inbound):
            shutil.copy2(src_inbound, os.path.join(dst_proto, "inbound.go"))
            print(f"  Copied {proto}/inbound.go")

    # 3. Create naive_user.go
    naive_dir = os.path.join(upstream_dir, "protocol/naive")
    os.makedirs(naive_dir, exist_ok=True)
    naive_user = os.path.join(naive_dir, "naive_user.go")
    with open(naive_user, "w") as f:
        f.write('''// SPDX-License-Identifier: MIT
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
	inbound := &Inbound{
		tag: tag,
	}
	err := inbound.UpdateUsers(ctx, options)
	if err != nil {
		return nil, err
	}
	return inbound, nil
}

func (n *Inbound) UpdateUsers(ctx context.Context, options option.NaiveInboundOptions) error {
	n.users = nil
	for _, user := range options.Users {
		n.users = append(n.users, auth.User{
			Username: user.Username,
			Password: user.Password,
		})
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

func (n *Inbound) ParseRequest(user auth.User, request string) (domain string, err error) {
	return "", nil
}

func (n *Inbound) SetTLS(config *tls.Config) {
	n.tlsConfig = config
}

func (n *Inbound) SetTLSPort(port uint16) {
	n.server = &port
}

func (n *Inbound) Type() string {
	return common.TypeInbound(n)
}
''')
    print("  Created naive_user.go")

    # 4. Create adapter/neighbor_entry.go
    adapter_dir = os.path.join(upstream_dir, "adapter")
    os.makedirs(adapter_dir, exist_ok=True)
    nbr_file = os.path.join(adapter_dir, "neighbor_entry.go")
    with open(nbr_file, "w") as f:
        f.write('''// SPDX-License-Identifier: MIT
// Copyright (C) 2025 V2BX contributors

package adapter

import "net/netip"

type NeighborEntry interface {
	GetDestination() netip.AddrPort
}
''')
    print("  Created adapter/neighbor_entry.go")

    # 5. Copy MoeclubM go.mod and go.sum
    for f in ["go.mod", "go.sum"]:
        src = os.path.join(moeclub_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(upstream_dir, f))
            print(f"  Copied {f}")

    # 6. Apply option file patches (MoeclubM versions with IsDomainName)
    option_files = {
        "option/dns.go": "option/dns.go",
        "outbound.go": "outbound.go",
        "tailscale.go": "tailscale.go",
        "transport/trojan/protocol.go": "transport/trojan/protocol.go",
    }
    for src_name, dst_name in option_files.items():
        src_path = os.path.join(moeclub_dir, src_name)
        if os.path.exists(src_path):
            os.makedirs(os.path.dirname(os.path.join(upstream_dir, dst_name)), exist_ok=True)
            shutil.copy2(src_path, os.path.join(upstream_dir, dst_name))
            print(f"  Copied {src_name}")

    # 7. Patch route/router.go - add GetCtx method
    router_file = os.path.join(upstream_dir, "route/router.go")
    if os.path.exists(router_file):
        with open(router_file) as f:
            content = f.read()
        if "func (r *Router) GetCtx()" not in content:
            content += "\n\nfunc (r *Router) GetCtx() context.Context {\n\treturn r.ctx\n}\n"
            with open(router_file, "w") as f:
                f.write(content)
            print("  Patched route/router.go with GetCtx()")

    # 8. Patch adapter/router.go - add GetCtx to Router interface
    router_adapter = os.path.join(upstream_dir, "adapter/router.go")
    if os.path.exists(router_adapter):
        with open(router_adapter) as f:
            content = f.read()
        if "GetCtx() context.Context" not in content:
            content = content.replace(
                "type Router interface {",
                "type Router interface {\n\tGetCtx() context.Context",
            )
            with open(router_adapter, "w") as f:
                f.write(content)
            print("  Patched adapter/router.go with GetCtx() interface")


def verify_build(source_dir: str) -> bool:
    """Verify the patched source builds successfully."""
    print("Verifying build...")
    env = os.environ.copy()
    env["GOEXPERIMENT"] = "jsonv2"
    env["CGO_ENABLED"] = "0"
    result = subprocess.run(
        ["go", "build", "-v", "-trimpath", "-o", "/tmp/sing-box-test", "./cmd/sing-box"],
        cwd=source_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        import os as os_module
        size = os_module.path.getsize("/tmp/sing-box-test")
        print(f"  Build successful! Binary size: {size / 1024 / 1024:.1f} MB")
        return True
    else:
        print(f"  Build FAILED:")
        print(result.stderr[-2000:])
        return False


def push_v2bx_tag(source_dir: str, upstream_tag: str, version_str: str):
    """Commit changes and push v2bx tag."""
    v2bx_tag = f"v{version_str}-v2bx.0"

    run(["git", "config", "--global", "user.email", "action@github.com"], cwd=source_dir)
    run(["git", "config", "--global", "user.name", "GitHub Action"], cwd=source_dir)
    run(["git", "checkout", "-b", V2BX_BRANCH], cwd=source_dir)
    run(["git", "add", "-A"], cwd=source_dir)

    # Check if there are changes
    result = run(["git", "diff", "--cached", "--quiet"], cwd=source_dir, check=False)
    if result.returncode == 0:
        print(f"No changes to commit for {v2bx_tag}")
        return v2bx_tag

    run(["git", "commit", "-m", f"V2BX: sync with sing-box {upstream_tag}"], cwd=source_dir)
    run(["git", "tag", "-a", v2bx_tag, "-m", f"V2BX: sync with sing-box {upstream_tag}"], cwd=source_dir)
    run(["git", "push", "origin", V2BX_BRANCH, "--force-with-lease"], cwd=source_dir)
    run(["git", "push", "origin", v2bx_tag], cwd=source_dir)
    print(f"Successfully pushed {v2bx_tag}")
    return v2bx_tag


def create_github_release(tag: str, upstream_tag: str):
    """Create a GitHub release via API."""
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("No GitHub token available, skipping release creation")
        return

    data = {
        "tag_name": tag,
        "name": f"sing-box-mod {tag} (based on {upstream_tag})",
        "body": f"""## V2BX Release {tag}

Based on [sing-box {upstream_tag}](https://github.com/{GITHUB_REPO}/releases/tag/{upstream_tag}).

### Changes
- Sync with upstream sing-box {upstream_tag}
- V2BX modifications applied

### Notes
This release is automatically generated.
""",
        "draft": False,
        "prerelease": False,
    }

    req = urllib.request.Request(
        f"https://api.github.com/repos/{MOD_REPO}/releases",
        data=json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            release = json.load(resp)
        print(f"Created release: {release['html_url']}")
    except urllib.error.HTTPError as e:
        if e.code == 422:  # Already exists
            print(f"Release {tag} already exists")
        else:
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Force re-sync even if tag exists")
    parser.add_argument("--dry-run", action="store_true", help="Don't push anything")
    args = parser.parse_args()

    workdir = WORKDIR
    if os.path.exists(workdir):
        import shutil
        shutil.rmtree(workdir)
    os.makedirs(workdir)

    print("=" * 60)
    print("V2BX Upstream Sync")
    print("=" * 60)

    # Step 1: Get latest upstream tag
    upstream_tag = get_latest_upstream_tag()
    version_str = upstream_tag.lstrip("v")
    v2bx_tag = f"v{version_str}-v2bx.0"

    # Step 2: Check if already exists
    if check_tag_exists(v2bx_tag) and not args.force:
        print(f"Tag {v2bx_tag} already exists, skipping. Use --force to re-sync.")
        # Still output the tag name so the build job can trigger
        with open(os.environ.get("GITHUB_OUTPUT", "/tmp/gha_output"), "a") as f:
            f.write(f"tag={v2bx_tag}\n")
            f.write(f"skipped=true\n")
        return

    # Step 3: Download official release
    upstream_dir = os.path.join(workdir, "sing-box")
    download_official_release(upstream_tag, upstream_dir)

    # Step 4: Fetch MoeclubM v1.13.1-v2bx.2 files
    moeclub_dir = os.path.join(workdir, "_moeclub")
    fetch_moeclub_v2bx_files(upstream_tag, workdir)

    # Step 5: Apply V2BX patches
    patch_upstream(upstream_dir, moeclub_dir)

    # Step 6: Verify build
    if not verify_build(upstream_dir):
        print("BUILD FAILED - not creating tag")
        sys.exit(1)

    # Step 7: Push tag
    if args.dry_run:
        print("Dry run - not pushing")
        return

    pushed_tag = push_v2bx_tag(upstream_dir, upstream_tag, version_str)

    # Step 8: Create GitHub release
    create_github_release(pushed_tag, upstream_tag)

    # Output for subsequent jobs
    with open(os.environ.get("GITHUB_OUTPUT", "/tmp/gha_output"), "a") as f:
        f.write(f"tag={pushed_tag}\n")
        f.write(f"upstream_tag={upstream_tag}\n")
        f.write(f"version={version_str}\n")
        f.write(f"skipped=false\n")

    print(f"\n✅ Sync complete: {pushed_tag}")


if __name__ == "__main__":
    main()
