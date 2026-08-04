### bash script to call DBQual python program ###
#echo "### ######################################### ###"
echo "### DaughterBoard Qualification - bash script ###"
#echo "### ######################################### ###"

current_date=$(date +'%Y/%m/%d')
current_time=$(date +'%H:%M:%S')

#echo "Current Date: ${current_date}"
#echo "Current Time: ${current_time}"
echo "Date - time | ${current_date} - ${current_time}"

wd=$(pwd)
#echo "Working Directory: ${wd}"

source myenv/bin/activate

#Check whether benchtest is currently being processed
curproc=$(mysql --login-path=tiledb tiledb -s -s -e "SELECT id from benchtest WHERE test_pass=2 LIMIT 1")
#echo "curproc = |${curproc}|"
if [[ "${curproc}" -gt 0 ]]; then
    echo "Found benchtest currently being processed, exiting to ensure no overlap."
    curproctest=$(mysql --login-path=tiledb tiledb -t -e "SELECT * from benchtest WHERE id = ${curproc}")
    echo "${curproctest}"
    #echo -e "Benchtest ID = ${curproc}\n"
    deactivate
    exit 0
fi

echo "No benchtests being processed, checking for unprocessed benchtests..."

#Check whether there are unprocessed benchtests
unproc=$(mysql --login-path=tiledb tiledb -s -s -e "SELECT id from benchtest WHERE test_pass=1 LIMIT 1")

if [[ "${unproc}" -gt 0 ]]; then
    echo "Found unprocessed benchtest:"
    unproctest=$(mysql --login-path=tiledb tiledb -t -e "SELECT * from benchtest WHERE id = ${unproc}")
    echo "${unproctest}"

    echo "Checking whether the unprocessed test is complete:"
    unproctestcomp=$(mysql --login-path=tiledb tiledb -s -s -e "SELECT test_stop from benchtest WHERE id = ${unproc}")
    #echo "VALUE IS ${unproctestcomp}"
    #printf 'Value: "%s"\n' "${unproctestcomp}"

    #if [[ -z "${unproctestcomp}" ]]; then
    if [[ "${unproctestcomp}" == "NULL" ]]; then
	echo "Unprocessed benchtest is still running (stop_time has returned 'NULL'). Exiting..."
	deactivate
	exit 0
    fi

    echo "Unprocessed test is complete. Switching processing flag:"
    mysql --login-path=tiledb tiledb -e "UPDATE benchtest SET test_pass = '2' WHERE id = ${unproc}"
    #unproctest=$(mysql --login-path=tiledb tiledb -t -e "SELECT * from benchtest WHERE id = ${unproc}")
    unproctest=$(mysql --login-path=tiledb tiledb -t -e "SELECT * from benchtest")
    echo "${unproctest}"

    echo "Processing..."
    # python3 DBQ_Mk5.py
    python3 DBQ_Mk6.py

    echo -e "Processing Complete!\n"
    mysql --login-path=tiledb tiledb -e "UPDATE benchtest SET test_pass = '3' WHERE id = ${unproc}"
    proctest=$(mysql --login-path=tiledb tiledb -t -e "SELECT * from benchtest")
    echo -e "${proctest}\n"

    # echo -e "Generating Production Plots!\n"
    # python3 production_plots.py
    deactivate
    exit
fi

source myenv/bin/activate
echo -e "Generating Production Plots!\n"
python3 production_plots_v1.py

echo -e "No unproccessed benchtests found. Exiting...\n"
deactivate
