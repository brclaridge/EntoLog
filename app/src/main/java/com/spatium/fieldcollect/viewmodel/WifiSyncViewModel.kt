package com.spatium.fieldcollect.viewmodel

import android.app.Application
import android.net.wifi.WifiManager
import androidx.lifecycle.AndroidViewModel
import com.spatium.fieldcollect.sync.SyncServer
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.net.Inet4Address
import java.net.NetworkInterface

class WifiSyncViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val PORT = 8080
    }

    private var server: SyncServer? = null

    private val _serverState = MutableStateFlow<ServerState>(ServerState.Idle)
    val serverState: StateFlow<ServerState> = _serverState

    fun startServer() {
        if (server != null) return
        try {
            val ip = getDeviceIp()
            if (ip == null) {
                _serverState.value = ServerState.Error("Not connected to WiFi")
                return
            }
            val srv = SyncServer(getApplication(), PORT)
            srv.start()
            server = srv
            _serverState.value = ServerState.Running(ip, PORT)
        } catch (e: Exception) {
            _serverState.value = ServerState.Error(e.message ?: "Failed to start server")
        }
    }

    fun stopServer() {
        server?.stop()
        server = null
        _serverState.value = ServerState.Idle
    }

    override fun onCleared() {
        super.onCleared()
        server?.stop()
        server = null
    }

    private fun getDeviceIp(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return null
            for (intf in interfaces) {
                if (!intf.isUp || intf.isLoopback) continue
                for (addr in intf.inetAddresses) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        return addr.hostAddress
                    }
                }
            }
        } catch (_: Exception) {}
        return null
    }

    sealed class ServerState {
        data object Idle : ServerState()
        data class Running(val ip: String, val port: Int) : ServerState()
        data class Error(val message: String) : ServerState()
    }
}
