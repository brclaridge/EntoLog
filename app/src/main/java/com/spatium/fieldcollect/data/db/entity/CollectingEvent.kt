package com.spatium.fieldcollect.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "collecting_events")
data class CollectingEvent(
    @PrimaryKey
    val uuid: String,
    val collectionCode: String,
    val latitude: Double?,
    val longitude: Double?,
    val elevation: Int?,
    val gpsAccuracy: Float?,
    val createdAt: String,       // ISO 8601
    val country: String,
    val stateProvince: String,
    val county: String,
    val locality: String,
    val host: String,
    val collectionTechnique: String? = null,
    val notes: String,
    val startDateTime: String? = null,   // ISO 8601, null for general events
    val endDateTime: String? = null,     // ISO 8601, null for general events
    val coordPrecision: Int = 5,         // decimal places for lat/lon (4, 5, or 6)
    val modifiedAt: String? = null       // ISO 8601 timestamp, for sync conflict resolution
)
