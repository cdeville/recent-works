#!/bin/bash

# Home Backup Script
# Creates a gzipped tarball of specified files/directories and uploads to Google Drive

# Exit on error
set -e  

# Define backup locations
BACKUP_DIR="${HOME}/Backups"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/home_backup_${TIMESTAMP}.tgz"
GDRIVE_REMOTE="gdrive:/Backups"

# files and directories to backup in home directory
BACKUP_ITEMS=(
    ".bash_profile"
    ".bash_aliases"
    ".bashrc"
    ".config"
    "bin"
    "Desktop"
    "Documents"
    "Music"
    "Notes"
    "OpenVPN"
    "Pictures"
    "Videos"
)

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

echo "Starting backup at $(date)"
echo "Backup file: ${BACKUP_FILE}"

# Build the list of existing items to backup
EXISTING_ITEMS=()
for item in "${BACKUP_ITEMS[@]}"
do
    if [ -e "${HOME}/${item}" ]
    then
        EXISTING_ITEMS+=("${item}")
        echo "  Including: ~/${item}"
    else
        echo "  Warning: ~/${item} does not exist, skipping"
    fi
done

# Check if there are any items to backup
if [ ${#EXISTING_ITEMS[@]} -eq 0 ]
then
    echo "Error: No items found to backup!"
    exit 1
fi

# Create the tarball
echo "Creating tarball..."
tar -czf "${BACKUP_FILE}" -C "${HOME}" "${EXISTING_ITEMS[@]}"

# Check if tarball was created successfully
if [ ! -f "${BACKUP_FILE}" ]
then
    echo "Error: Failed to create backup file!"
    exit 1
fi

# Get the size of the backup file
BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "Backup created successfully: ${BACKUP_SIZE}"

# Upload to Google Drive using rclone
echo "Uploading to Google Drive..."
if rclone copy "${BACKUP_FILE}" "${GDRIVE_REMOTE}" --progress
then
    echo "Upload completed successfully!"
    echo "Remote location: ${GDRIVE_REMOTE}/home_backup_${TIMESTAMP}.tgz"
else
    echo "Error: Upload failed!"
    exit 1
fi

echo "Backup completed at $(date)"
