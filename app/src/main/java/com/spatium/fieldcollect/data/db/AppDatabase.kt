package com.spatium.fieldcollect.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
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
    exportSchema = true
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun collectorDao(): CollectorDao
    abstract fun collectingEventDao(): CollectingEventDao
    abstract fun collectionTechniqueDao(): CollectionTechniqueDao
    abstract fun photoDao(): PhotoDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        /**
         * Every schema change needs a Migration here and a matching bump of the
         * @Database version. Without one Room throws on open rather than
         * dropping the tables — collecting events are field data that can't be
         * re-gathered, so failing loudly is the point.
         *
         *     private val MIGRATION_8_9 = object : Migration(8, 9) {
         *         override fun migrate(db: SupportSQLiteDatabase) {
         *             db.execSQL("ALTER TABLE collecting_events ADD COLUMN habitat TEXT NOT NULL DEFAULT ''")
         *         }
         *     }
         */
        private val MIGRATIONS: Array<Migration> = arrayOf()

        fun getInstance(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "fieldcollect.db"
                )
                    .addMigrations(*MIGRATIONS)
                    .build()
                    .also { INSTANCE = it }
            }
        }
    }
}
