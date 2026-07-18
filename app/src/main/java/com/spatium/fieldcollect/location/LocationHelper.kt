package com.spatium.fieldcollect.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.Locale
import kotlin.coroutines.resume

data class LocationResult(
    val latitude: Double,
    val longitude: Double,
    val elevation: Double,
    val accuracy: Float,
    val country: String,
    val stateProvince: String,
    val county: String,
    val locality: String
)

class LocationHelper(private val context: Context) {

    private val fusedClient = LocationServices.getFusedLocationProviderClient(context)

    suspend fun getCurrentLocation(): LocationResult? {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return null
        }

        val location = getLocation() ?: return null

        val geo = reverseGeocode(location.latitude, location.longitude)

        return LocationResult(
            latitude = location.latitude,
            longitude = location.longitude,
            elevation = location.altitude,
            accuracy = location.accuracy,
            country = geo.country,
            stateProvince = geo.stateProvince,
            county = geo.county,
            locality = geo.locality
        )
    }

    private suspend fun getLocation(): Location? = suspendCancellableCoroutine { cont ->
        try {
            val cts = CancellationTokenSource()
            fusedClient.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, cts.token)
                .addOnSuccessListener { location ->
                    cont.resume(location)
                }
                .addOnFailureListener {
                    cont.resume(null)
                }
            cont.invokeOnCancellation { cts.cancel() }
        } catch (e: SecurityException) {
            cont.resume(null)
        }
    }

    data class GeoResult(
        val country: String,
        val stateProvince: String,
        val county: String,
        val locality: String
    )

    @Suppress("DEPRECATION")
    fun reverseGeocode(lat: Double, lng: Double): GeoResult {
        return try {
            val geocoder = Geocoder(context, Locale.getDefault())
            val addresses = geocoder.getFromLocation(lat, lng, 1)
            if (!addresses.isNullOrEmpty()) {
                val addr = addresses[0]
                GeoResult(
                    country = addr.countryName ?: "",
                    stateProvince = abbreviateState(addr.adminArea ?: ""),
                    county = addr.subAdminArea ?: "",
                    locality = addr.locality ?: ""
                )
            } else {
                GeoResult("", "", "", "")
            }
        } catch (e: Exception) {
            GeoResult("", "", "", "")
        }
    }

    /**
     * Convert a full state/province name (as returned by the geocoder, e.g. "California")
     * to its postal abbreviation (e.g. "CA"). Matching is case-insensitive. Names not in
     * the map (e.g. international regions) are returned unchanged.
     */
    private fun abbreviateState(name: String): String {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return trimmed
        return STATE_ABBREVIATIONS[trimmed.lowercase(Locale.US)] ?: trimmed
    }

    companion object {
        private val STATE_ABBREVIATIONS: Map<String, String> = mapOf(
            // US states
            "alabama" to "AL", "alaska" to "AK", "arizona" to "AZ", "arkansas" to "AR",
            "california" to "CA", "colorado" to "CO", "connecticut" to "CT", "delaware" to "DE",
            "florida" to "FL", "georgia" to "GA", "hawaii" to "HI", "idaho" to "ID",
            "illinois" to "IL", "indiana" to "IN", "iowa" to "IA", "kansas" to "KS",
            "kentucky" to "KY", "louisiana" to "LA", "maine" to "ME", "maryland" to "MD",
            "massachusetts" to "MA", "michigan" to "MI", "minnesota" to "MN", "mississippi" to "MS",
            "missouri" to "MO", "montana" to "MT", "nebraska" to "NE", "nevada" to "NV",
            "new hampshire" to "NH", "new jersey" to "NJ", "new mexico" to "NM", "new york" to "NY",
            "north carolina" to "NC", "north dakota" to "ND", "ohio" to "OH", "oklahoma" to "OK",
            "oregon" to "OR", "pennsylvania" to "PA", "rhode island" to "RI", "south carolina" to "SC",
            "south dakota" to "SD", "tennessee" to "TN", "texas" to "TX", "utah" to "UT",
            "vermont" to "VT", "virginia" to "VA", "washington" to "WA", "west virginia" to "WV",
            "wisconsin" to "WI", "wyoming" to "WY",
            // US federal district and territories
            "district of columbia" to "DC", "puerto rico" to "PR", "guam" to "GU",
            "american samoa" to "AS", "u.s. virgin islands" to "VI",
            "united states virgin islands" to "VI", "northern mariana islands" to "MP",
            // Canadian provinces and territories
            "alberta" to "AB", "british columbia" to "BC", "manitoba" to "MB",
            "new brunswick" to "NB", "newfoundland and labrador" to "NL",
            "northwest territories" to "NT", "nova scotia" to "NS", "nunavut" to "NU",
            "ontario" to "ON", "prince edward island" to "PE", "quebec" to "QC",
            "québec" to "QC", "saskatchewan" to "SK", "yukon" to "YT"
        )
    }
}
