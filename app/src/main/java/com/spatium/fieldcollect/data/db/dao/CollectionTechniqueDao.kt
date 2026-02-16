package com.spatium.fieldcollect.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.spatium.fieldcollect.data.db.entity.CollectionTechnique
import kotlinx.coroutines.flow.Flow

@Dao
interface CollectionTechniqueDao {

    @Query("SELECT * FROM collection_techniques ORDER BY name ASC")
    fun getAll(): Flow<List<CollectionTechnique>>

    @Query("SELECT * FROM collection_techniques ORDER BY name ASC")
    suspend fun getAllSync(): List<CollectionTechnique>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(technique: CollectionTechnique): Long
}
