package com.spatium.fieldcollect.data.db.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

@Entity(
    tableName = "collecting_event_collector",
    primaryKeys = ["eventUuid", "collectorId"],
    foreignKeys = [
        ForeignKey(
            entity = CollectingEvent::class,
            parentColumns = ["uuid"],
            childColumns = ["eventUuid"],
            onDelete = ForeignKey.CASCADE
        ),
        ForeignKey(
            entity = Collector::class,
            parentColumns = ["id"],
            childColumns = ["collectorId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("collectorId")]
)
data class CollectingEventCollectorCrossRef(
    val eventUuid: String,
    val collectorId: Long
)
