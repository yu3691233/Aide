package cc.aidelink.app.service

import org.junit.Assert.assertEquals
import org.junit.Test


class WirelessAdbManagerTest {
    @Test
    fun rootedDevicePrefersClassicPort() {
        assertEquals(5555, selectAdbPort(preferClassic = true, classicPort = 5555, tlsPort = 43497))
    }

    @Test
    fun nonRootDevicePrefersTlsPort() {
        assertEquals(33761, selectAdbPort(preferClassic = false, classicPort = 5555, tlsPort = 33761))
    }

    @Test
    fun fallsBackWhenPreferredPortIsUnavailable() {
        assertEquals(43497, selectAdbPort(preferClassic = true, classicPort = 0, tlsPort = 43497))
        assertEquals(5555, selectAdbPort(preferClassic = false, classicPort = 5555, tlsPort = 0))
    }

    @Test
    fun wirelessCommandOnlyRunsOnTargetDevice() {
        assertEquals(true, shouldHandleWirelessAdbCommand("192.168.3.52", "192.168.3.52"))
        assertEquals(false, shouldHandleWirelessAdbCommand("192.168.3.52", "192.168.3.31"))
        assertEquals(true, shouldHandleWirelessAdbCommand("", "192.168.3.31"))
    }
}
