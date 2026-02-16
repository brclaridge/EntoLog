package com.spatium.fieldcollect.ui.adapter

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.spatium.fieldcollect.camera.CameraHelper
import com.spatium.fieldcollect.databinding.ItemRecordBinding

data class RecordItem(
    val uuid: String,
    val collectionCode: String,
    val title: String,
    val subtitle: String,
    val collectors: String,
    val firstPhotoPath: String? = null,
    val photoCount: Int = 0,
    val isTrap: Boolean = false
)

class RecordAdapter(
    private val onClick: (RecordItem) -> Unit,
    private val onLongClick: (RecordItem) -> Unit
) : ListAdapter<RecordItem, RecordAdapter.ViewHolder>(DIFF) {

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<RecordItem>() {
            override fun areItemsTheSame(a: RecordItem, b: RecordItem) = a.uuid == b.uuid
            override fun areContentsTheSame(a: RecordItem, b: RecordItem) = a == b
        }
    }

    inner class ViewHolder(private val binding: ItemRecordBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(item: RecordItem) {
            binding.tvRecordTitle.text = item.title
            binding.tvRecordUuid.text = item.collectionCode
            binding.tvRecordSubtitle.text = item.subtitle
            binding.tvRecordCollectors.text = item.collectors

            if (item.firstPhotoPath != null) {
                val bitmap = CameraHelper.loadBitmap(item.firstPhotoPath, sampleSize = 8)
                if (bitmap != null) {
                    binding.ivThumbnail.setImageBitmap(bitmap)
                    binding.ivThumbnail.visibility = View.VISIBLE
                } else {
                    binding.ivThumbnail.visibility = View.GONE
                }
            } else {
                binding.ivThumbnail.visibility = View.GONE
            }

            binding.root.setOnClickListener { onClick(item) }
            binding.root.setOnLongClickListener {
                onLongClick(item)
                true
            }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemRecordBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }
}
