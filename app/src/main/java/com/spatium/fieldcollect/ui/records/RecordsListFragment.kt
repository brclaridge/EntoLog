package com.spatium.fieldcollect.ui.records

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.core.os.bundleOf
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.spatium.fieldcollect.R
import com.spatium.fieldcollect.databinding.FragmentRecordsListBinding
import com.spatium.fieldcollect.ui.adapter.RecordAdapter
import com.spatium.fieldcollect.ui.adapter.RecordItem
import com.spatium.fieldcollect.util.DateUtils
import com.spatium.fieldcollect.viewmodel.CollectingEventViewModel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class RecordsListFragment : Fragment() {

    private var _binding: FragmentRecordsListBinding? = null
    private val binding get() = _binding!!

    private val viewModel: CollectingEventViewModel by viewModels()

    private lateinit var adapter: RecordAdapter

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentRecordsListBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        adapter = RecordAdapter(
            onClick = { item -> navigateToEdit(item) },
            onLongClick = { item -> showRecordOptions(item) }
        )

        binding.rvRecords.layoutManager = LinearLayoutManager(requireContext())
        binding.rvRecords.adapter = adapter

        viewLifecycleOwner.lifecycleScope.launch {
            viewModel.collectingEvents.collectLatest { events ->
                val items = events.map { ew ->
                    val e = ew.event
                    val photos = viewModel.getPhotos(e.uuid).first()
                    val locationParts = listOf(e.locality, e.county, e.stateProvince, e.country)
                        .filter { it.isNotBlank() }
                    val locationStr = locationParts.joinToString(", ").ifEmpty { "Collecting Event" }
                    val title = if (e.collectionTechnique != null) {
                        "${e.collectionTechnique} — $locationStr"
                    } else {
                        locationStr
                    }
                    val subtitle = if (e.startDateTime != null && e.endDateTime != null) {
                        "${DateUtils.formatForDisplay(e.startDateTime)} → ${DateUtils.formatForDisplay(e.endDateTime)}"
                    } else {
                        DateUtils.formatForDisplay(e.createdAt)
                    }
                    RecordItem(
                        uuid = e.uuid,
                        collectionCode = e.collectionCode,
                        title = title,
                        subtitle = subtitle,
                        collectors = ew.collectors.joinToString(", ") { it.name },
                        firstPhotoPath = photos.firstOrNull()?.filePath,
                        photoCount = photos.size,
                        isTrap = e.startDateTime != null
                    )
                }

                adapter.submitList(items)
                binding.tvEmpty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
            }
        }
    }

    private fun navigateToEdit(item: RecordItem) {
        val args = bundleOf("eventUuid" to item.uuid)
        if (item.isTrap) {
            findNavController().navigate(R.id.action_records_to_trap, args)
        } else {
            findNavController().navigate(R.id.action_records_to_specimen, args)
        }
    }

    private fun showRecordOptions(item: RecordItem) {
        val options = arrayOf(getString(R.string.duplicate), "Delete")
        MaterialAlertDialogBuilder(requireContext())
            .setTitle(item.collectionCode)
            .setItems(options) { _, which ->
                when (which) {
                    0 -> duplicateRecord(item)
                    1 -> confirmDelete(item)
                }
            }
            .show()
    }

    private fun duplicateRecord(item: RecordItem) {
        viewLifecycleOwner.lifecycleScope.launch {
            val newEvent = viewModel.duplicate(item.uuid)
            if (newEvent != null) {
                Toast.makeText(requireContext(), R.string.record_duplicated, Toast.LENGTH_SHORT).show()
                val args = bundleOf("eventUuid" to newEvent.uuid)
                if (item.isTrap) {
                    findNavController().navigate(R.id.action_records_to_trap, args)
                } else {
                    findNavController().navigate(R.id.action_records_to_specimen, args)
                }
            }
        }
    }

    private fun confirmDelete(item: RecordItem) {
        MaterialAlertDialogBuilder(requireContext())
            .setTitle("Delete ${item.collectionCode}?")
            .setMessage("This will delete the record and all its photos.")
            .setPositiveButton("Delete") { _, _ ->
                viewLifecycleOwner.lifecycleScope.launch {
                    viewModel.delete(item.uuid)
                }
                Toast.makeText(requireContext(), R.string.record_deleted, Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
