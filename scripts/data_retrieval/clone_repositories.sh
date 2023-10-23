#!/bin/bash

# Clone the repositories for a given year. Call with ./clone_repositories.sh <year>.
# The script will clone the repositories into the directory ../../repos.
# The script will also delete all files that are not Python or Python stub files.

# Set parameters
year=$1
index=0

# Set the data file name
data_file="github_data_$year.json"

# Set the base directory for cloning the repositories
base_dir="../../repos"

# Read the JSON data from the data file
data=$(cat "$data_file")

# Use jq to parse the JSON data and extract the repository information
repos=$(echo "$data" | jq -r '.[] | "\(.name) \(.url) \(.created_at)"')

# Loop through each repository
while read -r repo; do
    # Increment repository index
    index=$((index + 1))

    # Parse the repository information
    name=$(echo "$repo" | cut -d' ' -f1)
    url=$(echo "$repo" | cut -d' ' -f2)

    # Format the index as a zero-padded string
    echo "=== Downloading repo #$index..  $((index * 100 / 1000))% ==="

    # Set the target directory for cloning the repository
    target_dir="$base_dir/$year/$name"

    # Create the target directory
    mkdir -p "$target_dir"

    # Clone the repository into the target directory
    git clone --depth 1 "$url" "$target_dir"

    # Change to the target directory
    cd "$target_dir"

    # Find and delete all files that are not Python or Python stub files
    find . -type f ! \( -name '*.py' -o -name '*.pyi' \) -delete

    # Change back to the previous directory
    cd -
done <<< "$repos"

# Print a message to indicate that the repositories have been cloned
echo "Repositories cloned to $base_dir"

