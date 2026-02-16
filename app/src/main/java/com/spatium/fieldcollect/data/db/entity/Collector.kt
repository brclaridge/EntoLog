package com.spatium.fieldcollect.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "collectors")
data class Collector(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val name: String
)
