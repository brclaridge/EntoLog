package com.spatium.fieldcollect.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "photos")
data class Photo(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val recordUuid: String,     // links to either specimen or trap sample UUID
    val filePath: String,
    val createdAt: String       // ISO 8601
)
