package com.spatium.fieldcollect.data.db.entity

import androidx.room.Embedded
import androidx.room.Junction
import androidx.room.Relation

data class CollectingEventWithCollectors(
    @Embedded val event: CollectingEvent,
    @Relation(
        parentColumn = "uuid",
        entityColumn = "id",
        associateBy = Junction(
            value = CollectingEventCollectorCrossRef::class,
            parentColumn = "eventUuid",
            entityColumn = "collectorId"
        )
    )
    val collectors: List<Collector>
)
