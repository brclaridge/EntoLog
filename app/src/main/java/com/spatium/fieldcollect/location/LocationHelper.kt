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
                    stateProvince = addr.adminArea ?: "",
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
}
