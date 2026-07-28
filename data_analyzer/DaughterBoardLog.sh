### bash script to save and store DBQual logs ###
echo "### DaughterBoard Log - bash script ###"

dateref=$(date +"%Y%m%d")

date
echo "dateref = ${dateref}"

mv DBQ.log DBQLogs/DBQ_${dateref}.log
touch DBQ.log
