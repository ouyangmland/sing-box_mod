//go:build linux && !android

package route

import (
	"errors"
	"net/netip"
	"sync"
	"sync/atomic"
	"time"

	tun "github.com/sagernet/sing-tun"
	"github.com/sagernet/sing/common/control"
	E "github.com/sagernet/sing/common/exceptions"
	"github.com/sagernet/sing/common/logger"
	"github.com/sagernet/sing/common/x/list"

	"golang.org/x/sys/unix"
)

func newDefaultInterfaceMonitor(networkMonitor tun.NetworkUpdateMonitor, logger logger.Logger, options tun.DefaultInterfaceMonitorOptions) (tun.DefaultInterfaceMonitor, error) {
	return &linuxDefaultInterfaceMonitor{
		interfaceFinder: options.InterfaceFinder,
		networkMonitor:  networkMonitor,
		logger:          logger,
	}, nil
}

type linuxDefaultInterfaceMonitor struct {
	interfaceFinder  control.InterfaceFinder
	networkMonitor   tun.NetworkUpdateMonitor
	defaultInterface atomic.Pointer[control.Interface]
	noRoute          bool
	logger           logger.Logger

	checkUpdateTimer *time.Timer
	element          *list.Element[tun.NetworkUpdateCallback]

	callbackAccess sync.Mutex
	callbacks      list.List[tun.DefaultInterfaceUpdateCallback]

	myInterfaceAccess sync.Mutex
	myInterface       string
}

func (m *linuxDefaultInterfaceMonitor) Start() error {
	m.postCheckUpdate()
	m.element = m.networkMonitor.RegisterCallback(m.delayCheckUpdate)
	return nil
}

func (m *linuxDefaultInterfaceMonitor) delayCheckUpdate() {
	if m.checkUpdateTimer == nil {
		m.checkUpdateTimer = time.AfterFunc(time.Second, m.postCheckUpdate)
	} else {
		m.checkUpdateTimer.Reset(time.Second)
	}
}

func (m *linuxDefaultInterfaceMonitor) postCheckUpdate() {
	err := m.interfaceFinder.Update()
	if err != nil {
		m.logger.Error("update interface: ", err)
		return
	}
	err = m.checkUpdate()
	if errors.Is(err, tun.ErrNoRoute) {
		if !m.noRoute {
			m.noRoute = true
			m.defaultInterface.Store(nil)
			m.emit(nil, 0)
		}
	} else if err != nil {
		m.logger.Error("check interface: ", err)
	} else {
		m.noRoute = false
	}
}

func (m *linuxDefaultInterfaceMonitor) Close() error {
	if m.element != nil {
		m.networkMonitor.UnregisterCallback(m.element)
		m.element = nil
	}
	return nil
}

func (m *linuxDefaultInterfaceMonitor) DefaultInterface() *control.Interface {
	return m.defaultInterface.Load()
}

func (m *linuxDefaultInterfaceMonitor) OverrideAndroidVPN() bool {
	return false
}

func (m *linuxDefaultInterfaceMonitor) AndroidVPNEnabled() bool {
	return false
}

func (m *linuxDefaultInterfaceMonitor) RegisterCallback(callback tun.DefaultInterfaceUpdateCallback) *list.Element[tun.DefaultInterfaceUpdateCallback] {
	m.callbackAccess.Lock()
	defer m.callbackAccess.Unlock()
	return m.callbacks.PushBack(callback)
}

func (m *linuxDefaultInterfaceMonitor) UnregisterCallback(element *list.Element[tun.DefaultInterfaceUpdateCallback]) {
	m.callbackAccess.Lock()
	defer m.callbackAccess.Unlock()
	m.callbacks.Remove(element)
}

func (m *linuxDefaultInterfaceMonitor) emit(defaultInterface *control.Interface, flags int) {
	m.callbackAccess.Lock()
	callbacks := m.callbacks.Array()
	m.callbackAccess.Unlock()
	for _, callback := range callbacks {
		callback(defaultInterface, flags)
	}
}

func (m *linuxDefaultInterfaceMonitor) RegisterMyInterface(interfaceName string) {
	m.myInterfaceAccess.Lock()
	defer m.myInterfaceAccess.Unlock()
	m.myInterface = interfaceName
}

func (m *linuxDefaultInterfaceMonitor) MyInterface() string {
	m.myInterfaceAccess.Lock()
	defer m.myInterfaceAccess.Unlock()
	return m.myInterface
}

func (m *linuxDefaultInterfaceMonitor) checkUpdate() error {
	defaultInterface, err := m.getDefaultInterfaceBySocket()
	if err != nil {
		return err
	}
	if defaultInterface == nil {
		return tun.ErrNoRoute
	}
	newInterface, err := m.interfaceFinder.ByIndex(defaultInterface.Index)
	if err != nil {
		return E.Cause(err, "find updated interface: ", defaultInterface.Name)
	}
	oldInterface := m.defaultInterface.Swap(newInterface)
	if oldInterface != nil && oldInterface.Equals(*newInterface) {
		return nil
	}
	m.emit(newInterface, 0)
	return nil
}

func (m *linuxDefaultInterfaceMonitor) getDefaultInterfaceBySocket() (*control.Interface, error) {
	addr4, err4 := getLocalAddrForIPv4Route()
	if err4 == nil && addr4.IsValid() && !addr4.IsUnspecified() {
		return m.interfaceFinder.ByAddr(addr4)
	}
	addr6, err6 := getLocalAddrForIPv6Route()
	if err6 == nil && addr6.IsValid() && !addr6.IsUnspecified() {
		return m.interfaceFinder.ByAddr(addr6)
	}
	if err4 != nil && !errors.Is(err4, tun.ErrNoRoute) {
		return nil, err4
	}
	if err6 != nil && !errors.Is(err6, tun.ErrNoRoute) {
		return nil, err6
	}
	return nil, tun.ErrNoRoute
}

func getLocalAddrForIPv4Route() (netip.Addr, error) {
	fd, err := unix.Socket(unix.AF_INET, unix.SOCK_DGRAM, unix.IPPROTO_UDP)
	if err != nil {
		return netip.Addr{}, err
	}
	defer unix.Close(fd)
	err = unix.Connect(fd, &unix.SockaddrInet4{Addr: [4]byte{203, 0, 113, 1}, Port: 53})
	if err != nil {
		if errors.Is(err, unix.ENETUNREACH) || errors.Is(err, unix.EHOSTUNREACH) {
			return netip.Addr{}, tun.ErrNoRoute
		}
		return netip.Addr{}, err
	}
	sockname, err := unix.Getsockname(fd)
	if err != nil {
		return netip.Addr{}, err
	}
	sockaddr, ok := sockname.(*unix.SockaddrInet4)
	if !ok {
		return netip.Addr{}, E.New("unexpected sockname type")
	}
	addr := netip.AddrFrom4(sockaddr.Addr)
	if addr.IsUnspecified() {
		return netip.Addr{}, tun.ErrNoRoute
	}
	return addr, nil
}

func getLocalAddrForIPv6Route() (netip.Addr, error) {
	fd, err := unix.Socket(unix.AF_INET6, unix.SOCK_DGRAM, unix.IPPROTO_UDP)
	if err != nil {
		return netip.Addr{}, err
	}
	defer unix.Close(fd)
	err = unix.Connect(fd, &unix.SockaddrInet6{Addr: [16]byte{0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1}, Port: 53})
	if err != nil {
		if errors.Is(err, unix.ENETUNREACH) || errors.Is(err, unix.EHOSTUNREACH) {
			return netip.Addr{}, tun.ErrNoRoute
		}
		return netip.Addr{}, err
	}
	sockname, err := unix.Getsockname(fd)
	if err != nil {
		return netip.Addr{}, err
	}
	sockaddr, ok := sockname.(*unix.SockaddrInet6)
	if !ok {
		return netip.Addr{}, E.New("unexpected sockname type")
	}
	addr := netip.AddrFrom16(sockaddr.Addr)
	if addr.IsUnspecified() {
		return netip.Addr{}, tun.ErrNoRoute
	}
	return addr, nil
}
