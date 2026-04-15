//go:build !linux || android

package route

import (
	tun "github.com/sagernet/sing-tun"
	"github.com/sagernet/sing/common/logger"
)

func newDefaultInterfaceMonitor(networkMonitor tun.NetworkUpdateMonitor, logger logger.Logger, options tun.DefaultInterfaceMonitorOptions) (tun.DefaultInterfaceMonitor, error) {
	return tun.NewDefaultInterfaceMonitor(networkMonitor, logger, options)
}
