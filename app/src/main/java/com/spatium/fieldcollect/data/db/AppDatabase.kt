package com.spatium.fieldcollect.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import com.spatium.fieldcollect.data.db.dao.CollectionTechniqueDao
import com.spatium.fieldcollect.data.db.dao.CollectorDao
import com.spatium.fieldcollect.data.db.dao.CollectingEventDao
import com.spatium.fieldcollect.data.db.dao.PhotoDao

import com.spatium.fieldcollect.data.db.entity.CollectionTechnique
import com.spatium.fieldcollect.data.db.entity.Collector
import com.spatium.fieldcollect.data.db.entity.CollectingEvent
import com.spatium.fieldcollect.data.db.entity.CollectingEventCollectorCrossRef
import com.spatium.fieldcollect.data.db.entity.Photo

@Database(
    entities = [
        Collector::class,
        CollectingEvent::class,
        CollectingEventCollectorCrossRef::class,
        CollectionTechnique::class,
        Photo::class
    ],
    version = 8,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun collectorDao(): CollectorDao
    abstract fun collectingEventDao(): CollectingEventDao
    abstract fun collectionTechniqueDao(): CollectionTechniqueDao
    abstract fun photoDao(): PhotoDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "fieldcollect.db"
                )
                    .fallbackToDestructiveMigration()
                    .build()
                    .also { INSTANCE = it }
            }
        }
    }
}
