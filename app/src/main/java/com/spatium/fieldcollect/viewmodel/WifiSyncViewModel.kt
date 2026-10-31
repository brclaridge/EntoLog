package com.spatium.fieldcollect.viewmodel

import android.app.Application
import android.content.Context
import android.net.wifi.WifiManager
import androidx.lifecycle.AndroidViewModel
import com.spatium.fieldcollect.sync.SyncServer
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.net.Inet4Address
import java.net.NetworkInterface
import java.security.SecureRandom

class WifiSyncViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val PORT = 8080
        private const val PREFS_NAME = "fieldcollect_sync"
        private const val KEY_TOKEN = "pairing_token"
    }

    private var server: SyncServer? = null

    private val _serverState = MutableStateFlow<ServerState>(ServerState.Idle)
    val serverState: StateFlow<ServerState> = _serverState

    /**
     * Random per-install 4-digit pairing code the desktop app must send (as
     * the X-Sync-Token header) with every sync request. Without this, anyone
     * on the same WiFi network could read or overwrite collecting event data
     * and photos while the sync server is running. Kept short so it's easy
     * to type; SyncServer throttles repeated failed attempts to make
     * brute-forcing the 10,000 possible codes impractical during a sync
     * window.
     */
    private fun getOrCreatePairingToken(): String {
        val prefs = getApplication<Application>().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val existing = prefs.getString(KEY_TOKEN, null)
        // Only reuse a stored value if it's already a 4-digit code — discards
        // the old long hex tokens from earlier installs so they regenerate.
        if (existing != null && existing.matches(Regex("\\d{4}"))) return existing
        val token = "%04d".format(SecureRandom().nextInt(10000))
        prefs.edit().putString(KEY_TOKEN, token).apply()
        return token
    }

    fun startServer() {
        if (server != null) return
        try {
            val ip = getDeviceIp()
            if (ip == null) {
                _serverState.value = ServerState.Error("Not connected to WiFi")
                return
            }
            val token = getOrCreatePairingToken()
            val srv = SyncServer(getApplication(), PORT, token)
            srv.start()
            server = srv
            _serverState.value = ServerState.Running(ip, PORT, token)
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
        data class Running(val ip: String, val port: Int, val token: String) : ServerState()
        data class Error(val message: String) : ServerState()
    }
}
