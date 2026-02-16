package com.spatium.fieldcollect.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "trap_types")
data class TrapType(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val name: String
)
