#!/bin/bash

# Script to retrieve python repositories and store them so they can be cloned later.
# The script will retrieve the top 1000 repositories for each year between 2013 and 2022.
# Since the APIs results are inconsistent, the script will do the entire API call multiple times.
# To not overload the API, the script will wait 45 seconds between each API call and
# 2 minutes between each year.

# Set parameters
language=python     # Python repositories.
year_begin=2013     # Creation date of the repository.
year_end=2022
num_repos=1000      # The number of repos.
per_page=100        # GitHubs result limit.
iterations=5        # Do the entire API call multiple times.

# Calculate how many requests need to be made.
num_pages=$((num_repos / per_page))

for ((year = year_begin; year <= year_end; year++)); do

    for ((iteration = 0; iteration < iterations; iteration++)); do

        # Results will be stored in this array
        repos=()

        for ((page = 1; page <= num_pages; page++)); do
            # Set the GitHub API URL
            api_url="https://api.github.com/search/repositories?q=language:$language+stars:%3E10+created:$year-01-01..$year-12-31&sort=stars&order=desc&per_page=$per_page&page=$page"

            # Use curl to retrieve the data from the GitHub API
            data=$(curl --request GET \
                --url "$api_url")

            # Parse relevant information    
            repos_page=$(echo "$data" | jq -c '.items[] | {name: .full_name, url: .clone_url, stars: .stargazers_count, created_at: .created_at}')

            # Store that information in the array
            repos+=("$repos_page")
        done

        # Save data to json
        printf '%s\n' "${repos[@]}" | jq -s '.' > ./github_data_${year}_$iteration.json


        # Wait for API
        echo "$year Iteration: $iteration done. Waiting 45 seconds.."
        sleep 45s

    done

    echo "$year done. Waiting 2 minutes.."
    sleep 120s

done